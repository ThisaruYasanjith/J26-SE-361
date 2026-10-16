
package lk.sliit.codecleanliness.detection;

/**
 * Explicit preliminary God Class detection boundaries.
 *
 * These are caller-configured values, not calibrated
 * research thresholds or a claim of exact compatibility
 * with a published detection strategy.
 */
public record GodClassDetectionThresholds(
        int minWmc,
        int minAtfd,
        double maxTcc
) {

    public GodClassDetectionThresholds {

        if (minWmc < 1 || minAtfd < 1) {
            throw new IllegalArgumentException(
                    "WMC and ATFD boundaries must be positive"
            );
        }

        if (!Double.isFinite(maxTcc)
                || maxTcc < 0.0
                || maxTcc > 1.0) {

            throw new IllegalArgumentException(
                    "TCC boundary must be between 0 and 1"
            );
        }
    }
}
