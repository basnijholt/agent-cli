const { promisify } = require('util');
const { exec } = require('child_process');
const { promises: fs } = require('fs');
const execAsync = promisify(exec);

const debug = require('debug')('read-binary-file-arch');

// https://nodejs.org/api/process.html#processarch
const SUPPORTED_ARCH = [
  'arm',
  'arm64',
  'ia32',
  'loong64',
  'mips',
  'mipsel',
  'ppc',
  'ppc64',
  'riscv64',
  's390',
  's390x',
  'x64',
];

async function readPEArch(filePath) {
  const DOS_HEADER_PE_OFFSET = 0x3c;
  const COFF_HEADER_MACHINE_OFFSET = 4; // Offset after 'PE\0\0'
  const BUFFER_SIZE = 1024; // Enough to cover DOS header, PE header, and COFF header

  const buffer = Buffer.alloc(BUFFER_SIZE);
  const fileHandle = await fs.open(filePath, 'r');

  await fileHandle.read(buffer, 0, BUFFER_SIZE, 0);

  // Find the PE header offset from the DOS header
  const peOffset = buffer.readUInt32LE(DOS_HEADER_PE_OFFSET);

  // Read the machine type from the COFF header
  let machineType;
  try {
    machineType = buffer.readUInt16LE(
      peOffset + COFF_HEADER_MACHINE_OFFSET
    );
  } catch (error) {
    debug('read error:', error.message);
    throw new Error('Invalid PE file');
  }

  // Mapping of machine types to architectures
  const MACHINE_TYPES = {
    0x014c: 'ia32',
    0x8664: 'x64',
    0x01c0: 'arm',
    0x01c4: 'arm', // ARMv7 Thumb-2 LE
    0xaa64: 'arm64',
  };

  const arch = MACHINE_TYPES[machineType];
  debug('win32 arch:', arch);

  await fileHandle.close();

  return arch;
}

async function getArchUsingFileCommand(filePath) {
  const { stdout } = await execAsync(`file "${filePath}"`);
  const output = stdout.trim();
  debug('file command output:', output);

  const resultStart = filePath.length + 1; // skip 'filename:'
  const result = output.substring(resultStart).trim();
  debug('result:', result);

  // 'file' architectures => Node architectures
  const FILE_ARCH = {
    x64: 'x64',
    'x86-64': 'x64',
    x86_64: 'x64',
    x86: 'ia32',
    i386: 'ia32',
    arm64: 'arm64',
    arm: 'arm',
    aarch64: 'arm64',
    ARMv7: 'arm',
    ppc_7400: 'ppc',
    // PE32 executable (console) Intel 80386, for MS Windows
    'Intel 80386': 'ia32',
    // ELF 64-bit LSB executable, IA-64, version 1 (SYSV), dynamically linked, interpreter /lib/ld-linux-ia64.so.2, for GNU/Linux 2.6.16
    'IA-64': 'x64',
    // ELF 32-bit MSB executable, PowerPC or cisco 4500, version 1 (SYSV), dynamically linked, interpreter /lib/ld.so.1, for GNU/Linux 2.6.32
    PowerPC: 'ppc',
    // ELF 32-bit MSB executable, MIPS, MIPS-IV version 1 (SYSV), dynamically linked, interpreter /lib/ld.so.1, for GNU/Linux 2.4.1
    MIPS: 'mips',
  };

  const fileArchRegexStr = Object.keys(FILE_ARCH)
    .map((arch) => `(?:${arch})`)
    .join('|');
  const fileArchRegex = new RegExp(fileArchRegexStr);
  const fileArchMatch = result.match(fileArchRegex);
  debug('archMatch:', fileArchMatch && fileArchMatch[0]);
  const fileArch = fileArchMatch ? fileArchMatch[0] : null;
  const arch = FILE_ARCH[fileArch];

  return arch;
}

async function readBinaryFileArch(filePath) {
  const stat = await fs.stat(filePath);
  if (!stat.isFile()) {
    throw new Error(`${filePath} is not a file.`);
  }

  let arch;

  if (process.platform === 'win32') {
    // Windows only supports reading the architecture of valid PE files since
    // 'file' is not available.
    arch = await readPEArch(filePath);
  } else {
    arch = await getArchUsingFileCommand(filePath);
  }

  return SUPPORTED_ARCH.includes(arch) ? arch : null;
}

module.exports = { readBinaryFileArch };
