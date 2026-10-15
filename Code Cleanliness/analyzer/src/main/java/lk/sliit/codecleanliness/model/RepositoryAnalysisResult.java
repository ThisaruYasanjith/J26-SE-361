
package lk.sliit.codecleanliness.model;

import java.util.List;
import java.util.Objects;

public record RepositoryAnalysisResult(
        RepositoryParseResult parseResult,
        List<JavaTypeInfo> types,
        List<JavaRelationshipInfo> relationships,
        List<MaintainabilityFinding> findings
) {

    public RepositoryAnalysisResult {

        Objects.requireNonNull(parseResult, "Parse result is required");

        types = List.copyOf(
                Objects.requireNonNull(types, "Types are required")
        );

        relationships = List.copyOf(
                Objects.requireNonNull(
                        relationships,
                        "Relationships are required"
                )
        );

        findings = List.copyOf(
                Objects.requireNonNull(
                        findings,
                        "Findings are required"
                )
        );
    }

    // Preserves compatibility with the original
    // three-argument repository analysis result.
    public RepositoryAnalysisResult(
            RepositoryParseResult parseResult,
            List<JavaTypeInfo> types,
            List<JavaRelationshipInfo> relationships) {

        this(
                parseResult,
                types,
                relationships,
                List.of()
        );
    }

    public int totalFiles() {
        return parseResult.totalFiles();
    }

    public int parsedFiles() {
        return parseResult.successfulFiles();
    }

    public int failedFiles() {
        return parseResult.failedFileCount();
    }

    public int typeCount() {
        return types.size();
    }

    public int relationshipCount() {
        return relationships.size();
    }

    public int findingCount() {
        return findings.size();
    }
}
