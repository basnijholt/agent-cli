import { Arch } from "builder-util";
import { CancellationToken, Nullish, PublishConfiguration, PublishProvider } from "builder-util-runtime";
import { PublishContext, Publisher, PublishOptions, UploadTask } from "electron-publish";
import { MultiProgress } from "electron-publish/out/multiProgress";
import { AppInfo, PlatformSpecificBuildOptions } from "../index";
import { Packager } from "../packager";
import { PlatformPackager } from "../platformPackager";
export declare class PublishManager implements PublishContext {
    private readonly packager;
    private readonly publishOptions;
    readonly cancellationToken: CancellationToken;
    private readonly nameToPublisher;
    private readonly taskManager;
    readonly isPublish: boolean;
    readonly progress: MultiProgress | null;
    private readonly updateFileWriteTask;
    constructor(packager: Packager, publishOptions: PublishOptions, cancellationToken?: CancellationToken);
    private getAppInfo;
    getGlobalPublishConfigurations(): Promise<Array<PublishConfiguration> | null>;
    scheduleUpload(publishConfig: PublishConfiguration, event: UploadTask, appInfo: AppInfo): Promise<void>;
    private artifactCreatedWithoutExplicitPublishConfig;
    private getOrCreatePublisher;
    cancelTasks(): void;
    awaitTasks(): Promise<void>;
}
export declare function getAppUpdatePublishConfiguration(packager: PlatformPackager<any>, arch: Arch, errorIfCannot: boolean): Promise<{
    updaterCacheDirName: string;
    provider: PublishProvider;
    publisherName?: Array<string> | null;
    publishAutoUpdate?: boolean;
    requestHeaders?: import("http").OutgoingHttpHeaders;
    timeout?: number | null;
} | null>;
export declare function getPublishConfigsForUpdateInfo(packager: PlatformPackager<any>, publishConfigs: Array<PublishConfiguration> | null, arch: Arch | null): Promise<Array<PublishConfiguration> | null>;
export declare function createPublisher(context: PublishContext, version: string, publishConfig: PublishConfiguration, options: PublishOptions, packager: Packager): Promise<Publisher | null>;
export declare function computeDownloadUrl(publishConfiguration: PublishConfiguration, fileName: string | null, packager: PlatformPackager<any>): string;
export declare function getPublishConfigs(platformPackager: PlatformPackager<any>, targetSpecificOptions: PlatformSpecificBuildOptions | Nullish, arch: Arch | null, errorIfCannot: boolean): Promise<Array<PublishConfiguration> | null>;
