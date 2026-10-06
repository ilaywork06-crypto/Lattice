// Bidirectional text: Hebrew UI sentences carry English names and vice versa.
//
// Every value interpolated into a translation is wrapped in Unicode isolates
// (FSI … PDI), the plain-text twin of <bdi>: the value is laid out in its own
// direction and can't reorder the sentence around it ("נוצר 'Board A' (3)"
// instead of the parenthesis jumping sides). Markup uses <bdi> for the same job.

const FSI = '⁨'
const PDI = '⁩'
const ISOLATES = /[⁦-⁩]/g

/** Wrap a value in a first-strong isolate. */
export function isolate(value: string): string {
  return value ? `${FSI}${value}${PDI}` : value
}

/** The text without isolate marks — for values that go back into a form or the API. */
export function stripIsolates(value: string): string {
  return value.replace(ISOLATES, '')
}

function isolateParam(v: unknown): unknown {
  return typeof v === 'string' ? isolate(v) : v
}

/** Isolate the interpolation params of a `t(key, params, …)` call. */
export function isolateParams(args: unknown[]): unknown[] {
  const [key, params, ...rest] = args
  if (Array.isArray(params)) return [key, params.map(isolateParam), ...rest]
  if (params && typeof params === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(params as Record<string, unknown>)) out[k] = isolateParam(v)
    return [key, out, ...rest]
  }
  return args
}
