import type { NodeModuleInfo, DependencyTree, Dependency } from "./types";
import { Lazy } from "lazy-val";
export declare abstract class NodeModulesCollector<T extends Dependency<T, OptionalsType>, OptionalsType> {
    private readonly rootDir;
    private nodeModules;
    protected dependencyPathMap: Map<string, string>;
    protected allDependencies: Map<string, T>;
    constructor(rootDir: string);
    getNodeModules(): Promise<NodeModuleInfo[]>;
    abstract readonly installOptions: Promise<{
        cmd: string;
        args: string[];
        lockfile: string;
    }>;
    protected abstract readonly pmCommand: Lazy<string>;
    protected abstract getArgs(): string[];
    protected abstract parseDependenciesTree(jsonBlob: string): T;
    protected abstract extractProductionDependencyTree(tree: Dependency<T, OptionalsType>): DependencyTree;
    protected getDependenciesTree(): Promise<T>;
    protected extractRelevantData(npmTree: T): Dependency<T, OptionalsType>;
    protected extractInternal(deps: T["dependencies"]): T["dependencies"];
    protected resolvePath(filePath: string): string;
    private convertToDependencyGraph;
    private collectAllDependencies;
    private getTreeFromWorkspaces;
    private transToHoisterTree;
    private _getNodeModules;
}
