const semver = require("semver");

// These are sourced from here:
// https://nodejs.org/api/n-api.html#n_api_node_api_version_matrix
const nodeApiVersionRanges = [
  [">=24 || ^22.14 || ^23.6", 10],
  [">=21 || ^18.17 || ^20.3", 9],
  [">=16 || ^15.12 || ^12.22", 8],
  [">=15 || ^14.12 || ^12.19 || ^10.23", 7],
  [">=14 || ^12.17 || ^10.20", 6],
  [">=13 || ^12.11 || ^10.17", 5],
  [">=12 || ^11.8 || ^10.16", 4],
  [">=10", 3],
];

function fromNodeVersion(nodeVersion) {
  for (const [range, version] of nodeApiVersionRanges) {
    if (semver.satisfies(nodeVersion, range)) {
      return version;
    }
  }

  return undefined;
}

exports.fromNodeVersion = fromNodeVersion;

// These are populated via `yarn electron-versions`
const electronNapiVersions =
  // replace-start
  [
    ["35.0.0-beta.8", 10],
    ["35.0.0-alpha.1", 8],
    ["27.0.0-alpha.1", 9],
    ["15.0.0-alpha.1", 8],
    ["12.0.0-beta.1", 7],
    ["11.0.0-beta.1", 6],
    ["8.0.0-beta.1", 5],
    ["5.0.0-beta.1", 4],
    ["3.0.0-beta.1", 3],
  ];
// replace-end

function fromElectronVersion(electronVersion) {
  for (const [change, version] of electronNapiVersions) {
    if (semver.gte(electronVersion, change)) {
      return version;
    }
  }

  return undefined;
}

exports.fromElectronVersion = fromElectronVersion;
