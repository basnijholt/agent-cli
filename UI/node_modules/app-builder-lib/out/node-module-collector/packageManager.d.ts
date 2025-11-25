export type PM = "npm" | "yarn" | "pnpm" | "bun";
export declare const detect: ({ cwd, includeGlobalBun }?: {
    cwd?: string;
    includeGlobalBun?: boolean;
}) => Promise<PM>;
export declare function getPackageManagerVersion(pm: PM): Promise<string>;
export declare function clearCache(): void;
