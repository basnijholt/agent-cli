/**
 * Attempt to read the CPU architecture from a binary file.
 *
 * On Windows, only valid PE files are supported due to the 'file' command not
 * existing.
 * On Mac/Linux, all files are supported via the 'file' command.
 *
 * @param filePath
 */
export function readBinaryFileArch(
  filePath: string
): Promise<NodeJS.Process['arch'] | null>;
