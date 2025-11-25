import { NpmNodeModulesCollector } from "./npmNodeModulesCollector";
import { PnpmNodeModulesCollector } from "./pnpmNodeModulesCollector";
import { detect, PM, getPackageManagerVersion } from "./packageManager";
import { NodeModuleInfo } from "./types";
export declare function getCollectorByPackageManager(rootDir: string): Promise<NpmNodeModulesCollector | PnpmNodeModulesCollector>;
export declare function getNodeModules(rootDir: string): Promise<NodeModuleInfo[]>;
export { detect, getPackageManagerVersion, PM };
