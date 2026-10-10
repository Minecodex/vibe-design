type CamelCase<Key extends string> = Key extends `${infer Head}_${infer Tail}`
  ? `${Head}${Capitalize<CamelCase<Tail>>}`
  : Key

/** Optional canonical fields and their existing camelCase wire aliases. */
export type CompatibleWire<T> = Partial<T> & {
  [Key in keyof T as Key extends string ? CamelCase<Key> : Key]?: T[Key]
} & Record<string, unknown>
