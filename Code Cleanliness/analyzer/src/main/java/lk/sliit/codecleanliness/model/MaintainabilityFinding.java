
package lk.sliit.codecleanliness.model;

import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;

public record MaintainabilityFinding(

        String findingId,
        MaintainabilityConcern concern,
        FindingScope scope,

        Path sourceFile,
        String symbolName,

        int startLine,
        int endLine,

        String ruleId,
        String description,

        Map<String, String> evidence

) {

    public MaintainabilityFinding {

        if (findingId == null || findingId.isBlank()) {
            throw new IllegalArgumentException(
                    "Finding ID must not be blank"
            );
        }

        Objects.requireNonNull(concern, "Concern is required");
        Objects.requireNonNull(scope, "Scope is required");
        Objects.requireNonNull(sourceFile, "Source file is required");

        if (symbolName == null || symbolName.isBlank()) {
            throw new IllegalArgumentException(
                    "Symbol name must not be blank"
            );
        }

        if (startLine < 1 || endLine < startLine) {
            throw new IllegalArgumentException(
                    "Invalid source line range"
            );
        }

        if (ruleId == null || ruleId.isBlank()) {
            throw new IllegalArgumentException(
                    "Detection rule ID must not be blank"
            );
        }

        if (description == null || description.isBlank()) {
            throw new IllegalArgumentException(
                    "Finding description must not be blank"
            );
        }

        evidence = Map.copyOf(
                Objects.requireNonNull(
                        evidence,
                        "Evidence is required"
                )
        );
    }
}
