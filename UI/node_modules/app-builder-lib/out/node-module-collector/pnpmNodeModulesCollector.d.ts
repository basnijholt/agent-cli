import { Lazy } from "lazy-val";
import { NodeModulesCollector } from "./nodeModulesCollector";
import { DependencyTree, PnpmDependency } from "./types";
export declare class PnpmNodeModulesCollector extends NodeModulesCollector<PnpmDependency, PnpmDependency> {
    constructor(rootDir: string);
    static readonly pmCommand: Lazy<string>;
    protected readonly pmCommand: Lazy<string>;
    readonly installOptions: Promise<{
        cmd: string;
        args: string[];
        lockfile: string;
    }>;
    protected getArgs(): string[];
    protected extractRelevantData(npmTree: PnpmDependency): PnpmDependency;
    extractProductionDependencyTree(tree: PnpmDependency): DependencyTree;
    protected parseDependenciesTree(jsonBlob: string): PnpmDependency;
}
