# iconv-corefoundation

A Node.js library for character set conversion (like [iconv-lite](https://www.npmjs.com/package/iconv-lite)), using the macOS “Core Foundation” API.

This package contains a pre-compiled native add-on for Node.js, using N-API. See “System Requirements” below for details.

## Why?

`CoreFoundation.framework` contains, to my knowledge, the only character set converter supporting *all* of the legacy Macintosh scripts, including non-Apple ones (such as Mac OS Inuit) and double-byte scripts (such as Mac OS Japanese). If your Node.js program needs to handle these, and runs only on macOS, this package may be your best bet.

This is not intended for general character set conversion needs. Use iconv-lite for that; it's not limited to a single platform, it doesn't have any native code, and it's probably faster. This package is for when you specifically need to use Core Foundation's character set conversion facilities.

## License

iconv-corefoundation is provided under the terms of the MIT license. You can find the text of the MIT license in the [LICENSE](LICENSE) file.

## System Requirements

### Using

This package requires macOS, because it uses a macOS platform API (the Core Foundation framework) to do the actual work.

The native code portion of this package requires macOS 10.10 or newer.

This package requires [N-API](https://nodejs.org/dist/latest-v12.x/docs/api/n-api.html) version 3, which is available in Node.js versions 8.11.2, 10, and newer (but not 9).

### Building

Building this package isn't required to use it. Because this package only works on one platform, the native code is pre-compiled.

In addition to the system requirements for using this package, building it also requires the Xcode command-line tools to be installed. If they aren't, a window should appear offering to install them. If that doesn't work, run the command `xcode-select --install` to explicitly install them.

GCC does not seem to work; it fails to compile Core Foundation header files.

## API

[API documentation is in the `docs` folder.](docs/iconv-corefoundation.md)

The API for this package centers around the `StringEncoding` class. Each instance of this class represents a character encoding, such as ASCII or Mac OS Roman. To get a `StringEncoding` instance, call one of the static methods starting with `by`, such as `byCFStringEncoding`. (`StringEncoding` may not be constructed directly. It is instantiated only by native code.) Instances of `StringEncoding` have several informational properties (such as `ianaCharSetName`, the corresponding IANA character set name) and the methods `encode` and `decode`.

There are also several top-level functions exported by this package, like `transcode` (which converts one buffer to another, without creating a JavaScript string in between) and `encodeSmallest` (which encodes a string in the byte-wise smallest available encoding).

## Caveats

I have not benchmarked this code. I do not expect it to be fast. Encoding and decoding strings involves copying the string at least once, which is a fairly expensive operation, especially with large strings.

There is no streaming API. Core Foundation does not seem to have any notion of streaming character set conversion, so neither does this package.
