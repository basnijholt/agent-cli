import { Lazy } from "lazy-val";
import { NodeModulesCollector } from "./nodeModulesCollector";
import { DependencyTree, NpmDependency } from "./types";
export declare class NpmNodeModulesCollector extends NodeModulesCollector<NpmDependency, string> {
    constructor(rootDir: string);
    readonly pmCommand: Lazy<string>;
    readonly installOptions: Promise<{
        cmd: string;
        args: string[];
        lockfile: string;
    }>;
    protected getArgs(): string[];
    protected extractRelevantData(npmTree: NpmDependency): NpmDependency;
    protected extractProductionDependencyTree(tree: NpmDependency): DependencyTree;
    protected parseDependenciesTree(jsonBlob: string): NpmDependency;
}
