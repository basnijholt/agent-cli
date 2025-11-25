import { Arch } from "builder-util";
import { Nullish } from "builder-util-runtime";
import { Identity } from "../codeSign/macCodeSign";
import { Target } from "../core";
import { MacPackager } from "../macPackager";
import { PkgOptions } from "../options/pkgOptions";
export declare class PkgTarget extends Target {
    private readonly packager;
    readonly outDir: string;
    readonly options: PkgOptions;
    constructor(packager: MacPackager, outDir: string);
    build(appPath: string, arch: Arch): Promise<any>;
    private getExtraPackages;
    private customizeDistributionConfiguration;
    private buildComponentPackage;
}
export declare function prepareProductBuildArgs(identity: Identity | null, keychain: string | Nullish): Array<string>;
