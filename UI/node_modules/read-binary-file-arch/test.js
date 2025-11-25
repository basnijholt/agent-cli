const { promises: fs } = require('fs');
const path = require('path');
const degit = require('degit');
const { readBinaryFileArch } = require('.');

const samplesFolder = path.join(__dirname, 'samples');

async function before() {
  const emitter = degit('https://github.com/JonathanSalwan/binary-samples');
  emitter.on('info', console.debug);
  try {
    await emitter.clone(samplesFolder);
  } catch (error) {
    if (error.code !== 'DEST_NOT_EMPTY') {
      throw error;
    }
  }
}

async function test() {
  await before();

  const files = await fs.readdir(samplesFolder);
  for (const file of files) {
    const filePath = path.join(samplesFolder, file);

    try {
      const arch = await readBinaryFileArch(filePath);
      console.log(`${arch}\t${file}`);
    } catch (error) {
      console.error(`${file}: ${error.message}`);
    }
  }
}

test();
