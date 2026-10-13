package lk.sliit.codecleanliness.model;

import java.nio.file.Path;
import java.util.List;

public record MethodUsageInfo(
        Path sourceFile,
        String ownerType,
        String methodSignature,
        int line,
        List<String> accessedFields,
        List<String>calledMethods,
        List<String> unresolvedReferences
) {
    public MethodUsageInfo {
        accessedFields = List.copyOf(accessedFields);
        calledMethods = List.copyOf(calledMethods);
        unresolvedReferences = List.copyOf(unresolvedReferences);
    }
}