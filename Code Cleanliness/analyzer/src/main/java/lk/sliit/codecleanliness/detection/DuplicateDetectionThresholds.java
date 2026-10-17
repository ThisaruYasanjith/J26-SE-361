
package lk.sliit.codecleanliness.detection;

/**
 * Preliminary boundaries for exact normalized
 * method-body duplication detection.
 *
 * The existing candidate finder filters methods
 * shorter than ten normalized tokens.
 */
public record DuplicateDetectionThresholds(
        int minTokens,
        int minOccurrences
) {
    public DuplicateDetectionThresholds {
        if (minTokens < 10) {
            throw new IllegalArgumentException(
                    "Minimum token count must be at least 10"
            );
        }

        if (minOccurrences < 2) {
            throw new IllegalArgumentException(
                    "Minimum occurrences must be at least 2"
            );
        }
    }
}
