import { Filter } from "builder-util";
import { Minimatch } from "minimatch";
import { PlatformSpecificBuildOptions } from "./index";
export declare const excludedNames: string;
export declare const excludedExts: string;
export declare class FileMatcher {
    readonly macroExpander: (pattern: string) => string;
    readonly from: string;
    readonly to: string;
    readonly patterns: Array<string>;
    excludePatterns: Array<Minimatch> | null;
    readonly isSpecifiedAsEmptyArray: boolean;
    constructor(from: string, to: string, macroExpander: (pattern: string) => string, patterns?: Array<string> | string | null);
    normalizePattern(pattern: string): string;
    addPattern(pattern: string): void;
    prependPattern(pattern: string): void;
    isEmpty(): boolean;
    containsOnlyIgnore(): boolean;
    computeParsedPatterns(result: Array<Minimatch>, fromDir?: string): void;
    createFilter(): Filter;
    toString(): string;
}
export interface GetFileMatchersOptions {
    readonly macroExpander: (pattern: string) => string;
    readonly customBuildOptions: PlatformSpecificBuildOptions;
    readonly globalOutDir: string;
    readonly defaultSrc: string;
}
