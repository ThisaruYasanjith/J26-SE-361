
package lk.sliit.codecleanliness.detection;

/**
 * Explicit decision boundaries for preliminary method-level detection.
 *
 * These values must be supplied by the caller.
 * They are not automatically research-calibrated thresholds.
 */
public record MethodDetectionThresholds(
        int maxNcss,
        int maxCyclomaticComplexity
) {

    public MethodDetectionThresholds {

        if (maxNcss < 1) {
            throw new IllegalArgumentException(
                    "NCSS boundary must be positive"
            );
        }

        if (maxCyclomaticComplexity < 1) {
            throw new IllegalArgumentException(
                    "Complexity boundary must be positive"
            );
        }
    }
}
