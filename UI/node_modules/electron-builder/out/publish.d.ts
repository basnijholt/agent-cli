#! /usr/bin/env node
import { UploadTask } from "app-builder-lib";
import { Publish } from "app-builder-lib/out/core";
export declare function publish(args: {
    files: string[];
    version: string | undefined;
    configurationFilePath: string | undefined;
}): Promise<UploadTask[] | null>;
export declare function publishArtifactsWithOptions(uploadOptions: {
    file: string;
    arch: string | null;
}[], buildVersion?: string, configurationFilePath?: string, publishConfiguration?: Publish): Promise<UploadTask[] | null>;
