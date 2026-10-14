
package lk.sliit.codecleanliness.extraction;

import com.github.javaparser.JavaToken;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.stmt.BlockStmt;

import java.util.ArrayList;
import java.util.List;

public class JavaTokenNormalizer {

    public List<String> normalizeMethodBody(String methodBody) {

        BlockStmt body = StaticJavaParser.parseBlock(methodBody);

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
