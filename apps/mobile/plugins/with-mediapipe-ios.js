// MediaPipe's iOS pods ship static frameworks, but CocoaPods adds them to the
// app's link flags as plain libraries (-l), so the link fails with "library
// 'MediaPipeTasksCommon' not found". This rewrites those two flags to
// -framework in the app's Pods xcconfigs during pod install, through the
// CocoaPods API so the change is the one that gets saved.
const { withDangerousMod } = require("expo/config-plugins");
const fs = require("node:fs");
const path = require("node:path");

const MARKER = "# sajao: link MediaPipe as frameworks";
const SNIPPET = `
    ${MARKER}
    installer.aggregate_targets.each do |aggregate|
      aggregate.xcconfigs.each do |config_name, xcconfig|
        %w[MediaPipeTasksCommon MediaPipeTasksVision].each do |name|
          next unless xcconfig.libraries.delete?(name)
          xcconfig.frameworks.add(name)
        end
        xcconfig.save_as(aggregate.xcconfig_path(config_name))
      end
    end
`;

module.exports = function withMediaPipeIos(config) {
  return withDangerousMod(config, [
    "ios",
    async (modConfig) => {
      const podfile = path.join(modConfig.modRequest.platformProjectRoot, "Podfile");
      let text = fs.readFileSync(podfile, "utf8");
      if (!text.includes(MARKER)) {
        const hook = /post_install do \|installer\|\n/;
        if (!hook.test(text))
          throw new Error("with-mediapipe-ios: no post_install hook in the Podfile");
        text = text.replace(hook, (match) => match + SNIPPET);
        fs.writeFileSync(podfile, text);
      }
      return modConfig;
    },
  ]);
};
