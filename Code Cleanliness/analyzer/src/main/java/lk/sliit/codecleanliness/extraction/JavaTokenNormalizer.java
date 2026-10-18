
package lk.sliit.codecleanliness.extraction;

import com.github.javaparser.JavaParser;
import com.github.javaparser.JavaToken;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParseStart;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.Providers;
import com.github.javaparser.ast.stmt.BlockStmt;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class JavaTokenNormalizer {

    private final JavaParser parser;

    public JavaTokenNormalizer() {
        this(new ParserConfiguration()
                .setLanguageLevel(
                        ParserConfiguration.LanguageLevel.JAVA_17
                ));
    }

    public JavaTokenNormalizer(ParserConfiguration configuration) {
        this.parser = new JavaParser(
                Objects.requireNonNull(
                        configuration,
                        "Parser configuration is required"
                )
        );
    }

    public List<String> normalizeMethodBody(String methodBody) {

        if (methodBody == null || methodBody.isBlank()) {
            throw new IllegalArgumentException(
                    "Method body cannot be null or blank"
            );
        }

        ParseResult<BlockStmt> result = parser.parse(
                ParseStart.BLOCK,
                Providers.provider(methodBody)
        );

        if (!result.isSuccessful() || result.getResult().isEmpty()) {
            throw new IllegalArgumentException(
                    "Failed to parse Java method body: "
                            + result.getProblems()
            );
        }

        BlockStmt body = result.getResult().orElseThrow();

        List<String> normalized = new ArrayList<>();

        body.getTokenRange().orElseThrow().forEach(token -> {

            if (isTrivia(token)) {
                return;
            }

            String text = token.getText();

            if (text.matches(
                    "[A-Za-z_$][A-Za-z0-9_$]*"
            ) && !isJavaKeyword(text)) {

                normalized.add("IDENTIFIER");

            } else if (text.matches(
                    "[0-9]+([.][0-9]+)?"
            )) {

                normalized.add("NUMBER");

            } else if (text.startsWith("\"")
                    && text.endsWith("\"")) {

                normalized.add("STRING");

            } else {
                normalized.add(text);
            }
        });

        return List.copyOf(normalized);
    }

    private boolean isTrivia(JavaToken token) {
        return token.getCategory().isWhitespace()
                || token.getCategory().isComment();
    }

    private boolean isJavaKeyword(String text) {
        return switch (text) {
            case "abstract", "assert", "boolean", "break",
                 "byte", "case", "catch", "char", "class",
                 "const", "continue", "default", "do",
                 "double", "else", "enum", "extends", "final",
                 "finally", "float", "for", "goto", "if",
                 "implements", "import", "instanceof", "int",
                 "interface", "long", "native", "new",
                 "package", "private", "protected", "public",
                 "return", "short", "static", "strictfp",
                 "super", "switch", "synchronized", "this",
                 "throw", "throws", "transient", "try",
                 "void", "volatile", "while", "true", "false",
                 "null", "var", "record", "sealed",
                 "permits", "non-sealed", "yield" -> true;
            default -> false;
        };
    }
}
