import { Lazy } from "lazy-val";
export declare function createLazyProductionDeps<T extends boolean>(projectDir: string, excludedDependencies: Array<string> | null, flatten: T): Lazy<(T extends true ? NodeModuleInfo : NodeModuleDirInfo)[]>;
export interface NodeModuleDirInfo {
    readonly dir: string;
    readonly deps: Array<NodeModuleInfo>;
}
export interface NodeModuleInfo {
    readonly name: string;
    readonly version: string;
    readonly dir: string;
    readonly dependencies?: Array<NodeModuleInfo>;
}
