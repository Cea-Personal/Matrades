/** Compatibility declarations required by Next's URLPattern boundary. */
type URLPatternInput = string | URLPatternInit;
interface URLPatternOptions {
  ignoreCase?: boolean;
  baseURL?: string;
}
