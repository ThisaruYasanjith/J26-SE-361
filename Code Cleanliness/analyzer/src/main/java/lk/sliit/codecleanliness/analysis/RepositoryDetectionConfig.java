
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import java.util.Objects;

/**
 * Explicit configuration for the currently implemented
 * maintainability detectors.
 *
 * All thresholds are preliminary and require validation.
 */
public record RepositoryDetectionConfig(
        MethodDetectionThresholds methodThresholds,
        ClassDetectionThresholds classThresholds,
        CohesionDetectionThresholds cohesionThresholds,
        GodClassDetectionThresholds godClassThresholds
) {

    public RepositoryDetectionConfig {
        Objects.requireNonNull(
                methodThresholds,
                "Method thresholds are required"
        );

        Objects.requireNonNull(
                classThresholds,
                "Class thresholds are required"
        );

        Objects.requireNonNull(
                cohesionThresholds,
                "Cohesion thresholds are required"
        );

        Objects.requireNonNull(
                godClassThresholds,
                "God Class thresholds are required"
        );
    }
}
