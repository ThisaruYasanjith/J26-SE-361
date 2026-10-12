package lk.sliit.codecleanliness.model;

import java.util.List;
import java.util.Objects;

public record RepositoryAnalysisResult(
        RepositoryParseResult parseResult,
        List<JavaTypeInfo> types,
        List<JavaRelationshipInfo> relationships
) {
    public RepositoryAnalysisResult {
        Objects.requireNonNull(parseResult);
        types = List.copyOf(types);
        relationships = List.copyOf(relationships);
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
}
