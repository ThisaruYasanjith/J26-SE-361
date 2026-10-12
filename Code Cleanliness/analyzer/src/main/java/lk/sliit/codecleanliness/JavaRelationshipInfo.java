package lk.sliit.codecleanliness;

import java.nio.file.Path;

public record JavaRelationshipInfo(
        Path sourceFile,
        String sourceType,
        String sourceMethod,
        RelationshipKind kind,
        String target,
        ResolutionStatus status,
        int line
) {
    public enum RelationshipKind {
        EXTENDS,
        IMPLEMENTS,
        METHOD_CALL
    }

    public enum ResolutionStatus {
        RESOLVED,
        UNRESOLVED
    }
}