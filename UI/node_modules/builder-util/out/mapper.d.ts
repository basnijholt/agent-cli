type RecursiveMap = Map<any, RecursiveMap | any>;
export declare function mapToObject(map: RecursiveMap): any;
export declare function isValidKey(key: any): boolean;
export {};
