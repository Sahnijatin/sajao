/** @type {import('jest').Config} */
module.exports = {
  preset: "jest-expo",
  // Reanimated ships a resolver that swaps its native modules for JS ones in tests.
  resolver: "react-native-reanimated/jest/resolver",
  setupFilesAfterEnv: ["./jest.setup.js"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
};
