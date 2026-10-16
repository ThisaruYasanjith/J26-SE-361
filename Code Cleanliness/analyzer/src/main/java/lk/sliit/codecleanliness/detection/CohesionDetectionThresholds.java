
package lk.sliit.codecleanliness.detection;

/**
 * Explicit preliminary decision boundaries
 * for Weak Cohesion candidate detection.
 *
 * These boundaries require empirical calibration.
 */
public record CohesionDetectionThresholds(
        double maxTcc,
        int minLcom4
) {

    public CohesionDetectionThresholds {

        if (!Double.isFinite(maxTcc)
                || maxTcc < 0.0
                || maxTcc > 1.0) {

            throw new IllegalArgumentException(
                    "TCC boundary must be between 0 and 1"
            );
        }

        if (minLcom4 < 2) {
            throw new IllegalArgumentException(
                    "LCOM4 boundary must be at least 2"
            );
        }
    }
}
