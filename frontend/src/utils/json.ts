export function toPrettyJson(input: unknown): string {
  return JSON.stringify(input, null, 2)
}
