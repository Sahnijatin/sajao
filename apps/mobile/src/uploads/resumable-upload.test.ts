import { uploadSize } from "./photo-size";
import {
  PartUrlExpiredError,
  retryDelayMs,
  UploadGoneError,
  UploadInterruptedError,
  type UploadOptions,
  type UploadPlan,
  uploadResumable,
  type UploadsApi,
  type UploadStateStore,
} from "./resumable-upload";

const PART = 10; // A tiny part size keeps the tests readable.

/** A fake API plus storage: remembers which parts arrived, like the real one. */
function fakeServer() {
  const stored = new Map<number, number>(); // part number -> size
  let uploads = 0;
  let urlVersion = 1;
  let gone = false;
  const calls = { create: 0, resume: 0, complete: 0 };

  const plan = (size: number): UploadPlan => {
    const count = Math.max(1, Math.ceil(size / PART));
    return {
      key: `user/file-${uploads}.mp4`,
      upload_id: `upload-${uploads}`,
      part_size_bytes: PART,
      part_count: count,
      uploaded: [...stored].map(([part_number, size_bytes]) => ({
        part_number,
        size_bytes,
        etag: `etag-${part_number}`,
      })),
      parts: Array.from({ length: count }, (_, index) => index + 1)
        .filter((number) => !stored.has(number))
        .map((number) => ({ part_number: number, url: `part-${number}?v=${urlVersion}` })),
    };
  };

  const api: UploadsApi = {
    async create(file) {
      calls.create += 1;
      uploads += 1;
      stored.clear();
      gone = false;
      return plan(file.size_bytes);
    },
    async resume(ref) {
      calls.resume += 1;
      if (gone || ref.upload_id !== `upload-${uploads}`) throw new UploadGoneError();
      return plan(ref.size_bytes);
    },
    async complete(ref) {
      calls.complete += 1;
      gone = true;
      return {
        key: ref.key,
        size_bytes: ref.parts.reduce((total, part) => total + part.size_bytes, 0),
      };
    },
  };

  return {
    api,
    calls,
    stored,
    /** Signed URLs issued so far stop working. */
    expireUrls: () => (urlVersion += 1),
    forget: () => (gone = true),
    accept(url: string, body: ArrayBuffer) {
      const [name, version] = url.split("?v=");
      if (Number(version) !== urlVersion) throw new PartUrlExpiredError();
      const number = Number(name?.replace("part-", ""));
      stored.set(number, body.byteLength);
      return `etag-${number}`;
    },
  };
}

function memoryStore(): UploadStateStore & { saved: Map<string, unknown> } {
  const saved = new Map<string, { key: string; upload_id: string }>();
  return {
    saved,
    get: async (id) => saved.get(id) ?? null,
    set: async (id, state) => void saved.set(id, state),
    remove: async (id) => void saved.delete(id),
  };
}

function setup(sizeBytes: number) {
  const server = fakeServer();
  const store = memoryStore();
  const waits: number[] = [];
  const progress: number[] = [];
  const sliced: [number, number][] = [];
  const options: UploadOptions = {
    localId: "local-1",
    source: {
      kind: "video",
      contentType: "video/mp4",
      sizeBytes,
      slice: async (start, end) => {
        sliced.push([start, end]);
        return new ArrayBuffer(end - start);
      },
    },
    api: server.api,
    putPart: async (url, body) => server.accept(url, body as ArrayBuffer),
    store,
    onProgress: (sent) => progress.push(sent),
    wait: async (ms) => void waits.push(ms),
  };
  return { server, store, waits, progress, sliced, options };
}

describe("resumable upload", () => {
  it("sends every part in order and finishes", async () => {
    const { server, store, progress, sliced, options } = setup(25);

    const result = await uploadResumable(options);

    expect(result.key).toBe("user/file-1.mp4");
    expect(sliced).toEqual([
      [0, 10],
      [10, 20],
      [20, 25],
    ]);
    expect(progress).toEqual([0, 10, 20, 25]);
    expect(server.calls).toEqual({ create: 1, resume: 0, complete: 1 });
    expect(store.saved.size).toBe(0);
  });

  it("retries a failed part with backoff and carries on", async () => {
    const { server, waits, options } = setup(25);
    let failures = 2;
    const send = options.putPart;
    options.putPart = async (url, body) => {
      if (url.startsWith("part-2") && failures-- > 0) throw new Error("network down");
      return send(url, body);
    };

    await uploadResumable(options);

    expect(waits).toEqual([500, 1000]);
    expect([...server.stored.keys()]).toEqual([1, 2, 3]);
  });

  it("pauses without losing work when the network stays down, then resumes", async () => {
    const { server, store, sliced, progress, options } = setup(25);
    const send = options.putPart;
    let online = true;
    options.putPart = async (url, body) => {
      if (!online) throw new Error("network down");
      const etag = await send(url, body);
      if (url.startsWith("part-1")) online = false; // the connection drops after part 1
      return etag;
    };

    await expect(uploadResumable(options)).rejects.toBeInstanceOf(UploadInterruptedError);
    expect([...server.stored.keys()]).toEqual([1]);
    expect(store.saved.get("local-1")).toEqual({ key: "user/file-1.mp4", upload_id: "upload-1" });

    // Later, even after an app restart: same local id, the connection is back.
    online = true;
    sliced.length = 0;
    progress.length = 0;
    const result = await uploadResumable(options);

    expect(result.key).toBe("user/file-1.mp4");
    expect(server.calls.create).toBe(1);
    // Part 1 is not sent again.
    expect(sliced).toEqual([
      [10, 20],
      [20, 25],
    ]);
    expect(progress[0]).toBe(10);
    expect(store.saved.size).toBe(0);
  });

  it("asks for fresh signed URLs when they expire mid-upload", async () => {
    const { server, waits, options } = setup(25);
    const send = options.putPart;
    let expired = false;
    options.putPart = async (url, body) => {
      if (url.startsWith("part-2") && !expired) {
        expired = true;
        server.expireUrls();
      }
      return send(url, body);
    };

    await uploadResumable(options);

    expect(server.calls.resume).toBe(1);
    expect(waits).toEqual([]); // an expired URL is not a network problem: no backoff
    expect([...server.stored.keys()]).toEqual([1, 2, 3]);
  });

  it("starts over when the saved upload no longer exists", async () => {
    const { server, store, options } = setup(15);
    await store.set("local-1", { key: "user/old.mp4", upload_id: "expired" });

    const result = await uploadResumable(options);

    expect(server.calls).toEqual({ create: 1, resume: 1, complete: 1 });
    expect(result.key).toBe("user/file-1.mp4");
  });

  it("uploads a small photo as a single part", async () => {
    const { sliced, options } = setup(4);
    await uploadResumable(options);
    expect(sliced).toEqual([[0, 4]]);
  });

  it("backs off 0.5 s, 1 s, 2 s and never more than 8 s", () => {
    expect([1, 2, 3, 4, 5, 9].map(retryDelayMs)).toEqual([500, 1000, 2000, 4000, 8000, 8000]);
  });
});

describe("photo size for upload", () => {
  it("shrinks the long edge to 1600 px and keeps the shape", () => {
    expect(uploadSize({ width: 4000, height: 3000 })).toEqual({ width: 1600, height: 1200 });
    expect(uploadSize({ width: 3000, height: 4000 })).toEqual({ width: 1200, height: 1600 });
  });

  it("never enlarges a small photo", () => {
    expect(uploadSize({ width: 1200, height: 900 })).toEqual({ width: 1200, height: 900 });
    expect(uploadSize({ width: 1600, height: 1600 })).toEqual({ width: 1600, height: 1600 });
  });

  it("keeps very thin panoramas at least 1 px tall", () => {
    expect(uploadSize({ width: 20000, height: 4 })).toEqual({ width: 1600, height: 1 });
  });
});
