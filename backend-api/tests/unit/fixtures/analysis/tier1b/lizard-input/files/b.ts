export function pick(a: number, b: number): number {
  if (a > b && a > 0) {
    return a;
  }
  return b;
}
