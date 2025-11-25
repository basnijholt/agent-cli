import { NpmNodeModulesCollector } from "./npmNodeModulesCollector";
export declare class YarnNodeModulesCollector extends NpmNodeModulesCollector {
    constructor(rootDir: string);
    readonly installOptions: Promise<{
        cmd: string;
        args: string[];
        lockfile: string;
    }>;
}
