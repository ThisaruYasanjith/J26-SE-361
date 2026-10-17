
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.NamingDetectionConfig;

import java.util.Objects;

/**
 * Explicit repository maintainability detection configuration.
 *
 * The five SOLID risk detectors are opt-in and report
 * preliminary structural risk candidates, not verified
 * SOLID violations.
 *
 * All existing 4-, 5- and 6-argument constructors
 * remain supported.
 */
public record RepositoryDetectionConfig(
        MethodDetectionThresholds methodThresholds,
        ClassDetectionThresholds classThresholds,
        CohesionDetectionThresholds cohesionThresholds,
        GodClassDetectionThresholds godClassThresholds,
        DuplicateDetectionThresholds duplicateThresholds,
        NamingDetectionConfig namingConfig,
        boolean solidRisksEnabled
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
                null,
                false
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
                null,
                false
        );
    }

    public RepositoryDetectionConfig(
            MethodDetectionThresholds methodThresholds,
            ClassDetectionThresholds classThresholds,
            CohesionDetectionThresholds cohesionThresholds,
            GodClassDetectionThresholds godClassThresholds,
            DuplicateDetectionThresholds duplicateThresholds,
            NamingDetectionConfig namingConfig
    ) {
        this(
                methodThresholds,
                classThresholds,
                cohesionThresholds,
                godClassThresholds,
                duplicateThresholds,
                namingConfig,
                false
        );
    }

    public boolean duplicateDetectionEnabled() {
        return duplicateThresholds != null;
    }

    public boolean namingDetectionEnabled() {
        return namingConfig != null;
    }
}
