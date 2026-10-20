import type { Dictionary } from './types'

type MessageFn = (...args: never[]) => string

type Join<Prefix extends string, Key extends string> = `${Prefix}.${Key}`

type Paths<T> = T extends MessageFn
  ? never
  : T extends object
    ? {
        [K in keyof T & string]: T[K] extends MessageFn
          ? K
          : T[K] extends object
            ? string extends keyof T[K]
              ? K
              : K | Join<K, Paths<T[K]>>
            : K
      }[keyof T & string]
    : never

type ValueAt<T, P extends string> = P extends `${infer Head}.${infer Rest}`
  ? Head extends keyof T
    ? ValueAt<T[Head], Rest>
    : never
  : P extends keyof T
    ? T[P]
    : never

type DictionaryPaths = Paths<Dictionary>

type StringPaths = {
  [P in DictionaryPaths]: ValueAt<Dictionary, P> extends string ? P : never
}[DictionaryPaths]

type FunctionPaths = {
  [P in DictionaryPaths]: ValueAt<Dictionary, P> extends MessageFn ? P : never
}[DictionaryPaths]

type Arguments<P extends FunctionPaths> = ValueAt<Dictionary, P> extends (...input: infer A) => string ? A : []

export interface Translator {
  (path: StringPaths): string
  <P extends FunctionPaths>(path: P, ...args: Arguments<P>): string
}

function resolve(messages: Dictionary, path: string): unknown {
  return path.split('.').reduce<unknown>((node, key) => {
    if (node !== null && typeof node === 'object' && key in node) {
      return (node as Record<string, unknown>)[key]
    }
    return undefined
  }, messages)
}

/** Read a dictionary leaf. Function leaves receive the remaining arguments. */
export function translate(messages: Dictionary, path: string, ...args: unknown[]): string {
  const value = resolve(messages, path)
  if (typeof value === 'function') {
    return (value as (...input: unknown[]) => string)(...args)
  }
  return typeof value === 'string' ? value : path
}
