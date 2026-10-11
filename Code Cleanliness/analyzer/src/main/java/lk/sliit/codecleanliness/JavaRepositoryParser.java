package lk.sliit.codecleanliness;

import com.github.javaparser.ast.CompilationUnit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class JavaRepositoryParser {

    private final JavaRepositoryScanner scanner;
    private final JavaSourceParser parser;

    public JavaRepositoryParser() {
        this(new JavaRepositoryScanner(), new JavaSourceParser());
    }

    public JavaRepositoryParser(
            JavaRepositoryScanner scanner,
            JavaSourceParser parser) {

        this.scanner = Objects.requireNonNull(scanner);
        this.parser = Objects.requireNonNull(parser);
    }

    public RepositoryParseResult parseRepository(Path root)
            throws IOException {

        return parseFiles(root, parser);
    }

    public RepositoryParseResult parseRepositoryWithSymbols(
            Path root) throws IOException {

        // Repository-specific symbol solver configuration.
        RepositorySymbolResolver resolver =
                new RepositorySymbolResolver(root);

        JavaSourceParser symbolAwareParser =
                new JavaSourceParser(
                        resolver.createParserConfiguration()
                );

        return parseFiles(root, symbolAwareParser);
    }

    private RepositoryParseResult parseFiles(
            Path root,
            JavaSourceParser activeParser) throws IOException {

        List<Path> javaFiles = scanner.scan(root);

        Map<Path, CompilationUnit> parsed =
                new LinkedHashMap<>();

        Map<Path, String> failures =
                new LinkedHashMap<>();

        for (Path file : javaFiles) {

            try {
                String source = Files.readString(
                        file,
                        StandardCharsets.UTF_8
                );

                CompilationUnit unit =
                        activeParser.parse(source);

                unit.setStorage(file);

                parsed.put(file, unit);

            } catch (IOException | IllegalArgumentException ex) {
                failures.put(file, ex.toString());
            }
        }

        return new RepositoryParseResult(
                root.toAbsolutePath().normalize(),
                javaFiles,
                parsed,
                failures
        );
    }
}