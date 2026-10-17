
package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;

import java.util.Objects;

/**
 * Explicit preliminary maintainability detection settings.
 *
 * The four-argument constructor is preserved for existing
 * callers. Duplication detection requires explicit opt-in
 * through the five-argument constructor.
 */
public record RepositoryDetectionConfig(
        MethodDetectionThresholds methodThresholds,
        ClassDetectionThresholds classThresholds,
        CohesionDetectionThresholds cohesionThresholds,
        GodClassDetectionThresholds godClassThresholds,
        DuplicateDetectionThresholds duplicateThresholds
) {

    public RepositoryDetectionConfig {
        Objects.requireNonNull(methodThresholds);
        Objects.requireNonNull(classThresholds);
        Objects.requireNonNull(cohesionThresholds);
        Objects.requireNonNull(godClassThresholds);
    }

    /**
     * Previous configuration remains compatible.
     * A null duplication configuration means disabled.
     */
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
                null
        );
    }

    public boolean duplicateDetectionEnabled() {
        return duplicateThresholds != null;
    }
}
