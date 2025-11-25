import { SnapStoreOptions } from "builder-util-runtime/out/publishOptions";
import { PublishContext, UploadTask } from ".";
import { Publisher } from "./publisher";
export declare class SnapStorePublisher extends Publisher {
    private options;
    readonly providerName = "snapStore";
    constructor(context: PublishContext, options: SnapStoreOptions);
    upload(task: UploadTask): Promise<any>;
    toString(): string;
}
