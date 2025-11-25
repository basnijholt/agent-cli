[![NPM version](https://badge.fury.io/js/pe-library.svg)](https://www.npmjs.com/package/pe-library)
[![Build Status](https://github.com/jet2jet/pe-library-js/actions/workflows/main-ci.yml/badge.svg)](https://github.com/jet2jet/pe-library-js)

# pe-library

pe-library provides parsing and generating Portable Executable (known as Windows Executables) binaries.

## Usage

```js
import * as PE from 'pe-library';
import * as fs from 'fs';

// load and parse data
let data = fs.readFileSync('MyApp.exe');
// (the Node.js Buffer instance can be specified directly to NtExecutable.from)
let exe = PE.NtExecutable.from(data);

// get section data
let exportSection = exe.getSectionByEntry(PE.Format.ImageDirectoryEntry.Export);
// read binary data stored in exportSection.data ...
// to write binary: use exe.setSectionByEntry

// write to buffer
let newBin = exe.generate();
fs.writeFileSync('MyApp_modified.exe', new Buffer(newBin));
```

## License

- All programs / source codes / binaries in this package, EXCEPT FOLLOWINGS, are licensed with [MIT License](./LICENSE).
- The followings are licensed with 0-BSD license:
  - [tools/dos-stub/dos-stub.asm](./tools/dos-stub/dos-stub.asm)
  - The bit code, generated from tools/dos-stub/dos-stub.asm, written in [src/main/util/generate.ts](./src/main/util/generate.ts) as `DOS_STUB_PROGRAM`
