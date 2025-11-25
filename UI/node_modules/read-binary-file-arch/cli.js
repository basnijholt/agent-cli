#!/usr/bin/env node
const { readBinaryFileArch } = require('.');

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 1) {
    console.log('Usage: read-binary-file-arch <path-to-file>');
    process.exit(1);
  }
  const filePath = args[0];

  try {
    const arch = await readBinaryFileArch(filePath);
    console.log(arch);
  } catch (error) {
    console.error(error.message);
  }
}

main();
