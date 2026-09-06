/**
 * cn — class name utility (single responsibility: compose conditional classes)
 * Pure, no side effects. Dependency-free to keep bundle token-small.
 */
export type ClassValue = string | false | null | undefined | 0;

export function cn(...classes: ClassValue[]): string {
  return classes.filter(Boolean).join(' ');
}
