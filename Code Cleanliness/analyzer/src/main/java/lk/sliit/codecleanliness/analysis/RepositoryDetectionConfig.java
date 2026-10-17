
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.NamingDetectionConfig;

import java.util.Objects;

/**
 * Explicit preliminary maintainability detection settings.
 *
 * Optional duplication and naming checks must be enabled
 * by supplying their configurations.
 *
 * Existing four- and five-argument constructors are preserved.
 */
public record RepositoryDetectionConfig(
        MethodDetectionThresholds methodThresholds,
        ClassDetectionThresholds classThresholds,
        CohesionDetectionThresholds cohesionThresholds,
        GodClassDetectionThresholds godClassThresholds,
        DuplicateDetectionThresholds duplicateThresholds,
        NamingDetectionConfig namingConfig
) {

    public RepositoryDetectionConfig {
        Objects.requireNonNull(
                methodThresholds, "Method thresholds are required"
        );
        Objects.requireNonNull(
                classThresholds, "Class thresholds are required"
        );
        Objects.requireNonNull(
                cohesionThresholds, "Cohesion thresholds are required"
        );
        Objects.requireNonNull(
                godClassThresholds, "God Class thresholds are required"
        );
    }

    public RepositoryDetectionConfig(
            MethodDetectionThresholds methodThresholds,
            ClassDetectionThresholds classThresholds,
            CohesionDetectionThresholds cohesionThresholds,
            GodClassDetectionThresholds godClassThresholds
    ) {
        this(
                methodThresholds,
                classThresholds,
                cohesionThresholds,
                godClassThresholds,
                null,
                null
        );
    }

    public RepositoryDetectionConfig(
            MethodDetectionThresholds methodThresholds,
            ClassDetectionThresholds classThresholds,
            CohesionDetectionThresholds cohesionThresholds,
            GodClassDetectionThresholds godClassThresholds,
            DuplicateDetectionThresholds duplicateThresholds
    ) {
        this(
                methodThresholds,
                classThresholds,
                cohesionThresholds,
                godClassThresholds,
                duplicateThresholds,
                null
        );
    }

    public boolean duplicateDetectionEnabled() {
        return duplicateThresholds != null;
    }

    public boolean namingDetectionEnabled() {
        return namingConfig != null;
    }
}
