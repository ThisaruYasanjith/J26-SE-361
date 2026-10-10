package lk.sliit.codecleanliness;

import com.github.javaparser.ast.CompilationUnit;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public record RepositoryParseResult(
        Path repositoryRoot,
        List<Path> discoveredFiles,
        Map<Path, CompilationUnit> parsedFiles,
        Map<Path, String> failedFiles
) {
    public RepositoryParseResult {
        discoveredFiles = List.copyOf(discoveredFiles);
        parsedFiles = Map.copyOf(parsedFiles);
        failedFiles = Map.copyOf(failedFiles);
    }

    public int totalFiles() {
        return discoveredFiles.size();
    }

    public int successfulFiles() {
        return parsedFiles.size();
    }

    public int failedFileCount() {
        return failedFiles.size();
    }
}