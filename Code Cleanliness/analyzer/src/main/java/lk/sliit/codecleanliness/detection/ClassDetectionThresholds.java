
package lk.sliit.codecleanliness.detection;

/**
 * Configurable, preliminary class-size decision boundaries.
 *
 * These boundaries require empirical calibration before
 * they can be treated as validated smell-detection rules.
 */
public record ClassDetectionThresholds(
        int maxClassNcss,
        int maxMethodCount,
        int maxFieldCount
) {

    public ClassDetectionThresholds {

        if (maxClassNcss < 1
                || maxMethodCount < 1
                || maxFieldCount < 1) {

            throw new IllegalArgumentException(
                    "Class detection boundaries must be positive"
            );
        }
    }
}
