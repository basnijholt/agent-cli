export interface NodeModuleInfo {
    name: string;
    version: string;
    dir: string;
    dependencies?: Array<NodeModuleInfo>;
}
export type ParsedDependencyTree = {
    readonly name: string;
    readonly version: string;
    readonly path: string;
    readonly workspaces?: string[];
};
export interface DependencyTree extends Omit<Dependency<DependencyTree, DependencyTree>, "optionalDependencies"> {
    readonly implicitDependenciesInjected: boolean;
}
export interface PnpmDependency extends Dependency<PnpmDependency, PnpmDependency> {
}
export interface NpmDependency extends Dependency<NpmDependency, string> {
    readonly _dependencies?: {
        [packageName: string]: string;
    };
}
export type Dependency<T, V> = Dependencies<T, V> & ParsedDependencyTree;
export type Dependencies<T, V> = {
    readonly dependencies?: {
        [packageName: string]: T;
    };
    readonly optionalDependencies?: {
        [packageName: string]: V;
    };
};
export interface DependencyGraph {
    [packageNameAndVersion: string]: PackageDependencies;
}
interface PackageDependencies {
    readonly dependencies: string[];
}
export {};
