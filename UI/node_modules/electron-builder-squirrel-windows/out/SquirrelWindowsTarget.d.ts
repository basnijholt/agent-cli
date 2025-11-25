import { Arch, SquirrelWindowsOptions, Target, WinPackager } from "app-builder-lib";
import { Options as SquirrelOptions } from "electron-winstaller";
export default class SquirrelWindowsTarget extends Target {
    private readonly packager;
    readonly outDir: string;
    readonly options: SquirrelWindowsOptions;
    constructor(packager: WinPackager, outDir: string);
    private prepareSignedVendorDirectory;
    build(appOutDir: string, arch: Arch): Promise<void>;
    private get appName();
    private select7zipArch;
    private createNuspecTemplateWithProjectUrl;
    computeEffectiveDistOptions(appDirectory: string, outputDirectory: string, setupFile: string): Promise<SquirrelOptions>;
}
