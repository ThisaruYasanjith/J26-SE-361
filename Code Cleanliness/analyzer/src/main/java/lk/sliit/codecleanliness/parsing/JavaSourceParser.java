package lk.sliit.codecleanliness.parsing;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;

import java.util.Objects;

public class JavaSourceParser {

    private final JavaParser parser;

    public JavaSourceParser() {
        this(new ParserConfiguration()
                .setLanguageLevel(
                        ParserConfiguration.LanguageLevel.JAVA_17
                ));
    }

    public JavaSourceParser(ParserConfiguration configuration) {
        this.parser = new JavaParser(
                Objects.requireNonNull(configuration)
        );
    }

    public CompilationUnit parse(String sourceCode) {

        if (sourceCode == null || sourceCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Java source code cannot be null or empty."
            );
        }

        ParseResult<CompilationUnit> result =
                parser.parse(sourceCode);

        if (!result.isSuccessful() ||
                result.getResult().isEmpty()) {
            throw new IllegalArgumentException(
                    "Failed to parse Java source: " +
                            result.getProblems()
            );
        }

        return result.getResult().get();
    }
}
