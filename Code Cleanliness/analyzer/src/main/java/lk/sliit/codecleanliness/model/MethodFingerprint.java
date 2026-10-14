package lk.sliit.codecleanliness.model;

import java.nio.file.Path;

public record MethodFingerprint(
        Path sourceFile,
        String ownerType,
        String methodSignature,
        int line,
        int tokenCount,
        String fingerprint
) {}