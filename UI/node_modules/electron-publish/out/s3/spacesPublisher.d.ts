import { SpacesOptions } from "builder-util-runtime";
import { PublishContext } from "../";
import { BaseS3Publisher } from "./baseS3Publisher";
export declare class SpacesPublisher extends BaseS3Publisher {
    private readonly info;
    readonly providerName = "spaces";
    constructor(context: PublishContext, info: SpacesOptions);
    static checkAndResolveOptions(options: SpacesOptions, channelFromAppVersion: string | null, errorIfCannot: boolean): Promise<void>;
    protected getBucketName(): string;
    protected configureS3Options(args: Array<string>): void;
}
