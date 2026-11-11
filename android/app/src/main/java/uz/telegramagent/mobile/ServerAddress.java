package uz.telegramagent.mobile;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

final class ServerAddress {
    static String validate(String value) {
        String candidate = value.trim();
        if (!candidate.contains("://")) {
            candidate = (candidate.matches("[0-9.]+(?::[0-9]+)?/?") ? "http://" : "https://") + candidate;
        }
        try {
            URI uri = new URI(candidate);
            String scheme = uri.getScheme().toLowerCase(Locale.ROOT);
            String host = uri.getHost();
            if (host == null || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null ||
                (uri.getPath() != null && !uri.getPath().isEmpty() && !uri.getPath().equals("/")) ||
                uri.getPort() > 65535 || uri.getPort() == 0) {
                throw new IllegalArgumentException("Serverning asosiy manzilini kiriting.");
            }
            if (!"https".equals(scheme) && !("http".equals(scheme) && privateHost(host))) {
                throw new IllegalArgumentException("Server uchun HTTPS yoki Wi-Fi uchun mahalliy IP kiriting.");
            }
            int port = uri.getPort();
            if (port == 443 && scheme.equals("https") || port == 80 && scheme.equals("http")) port = -1;
            return new URI(scheme, null, host.toLowerCase(Locale.ROOT), port, "/", null, null).toString();
        } catch (URISyntaxException error) { throw new IllegalArgumentException("Manzil noto‘g‘ri."); }
    }

    static boolean sameOrigin(String server, String target) {
        try {
            URI wanted = new URI(server), actual = new URI(target);
            return wanted.getScheme().equalsIgnoreCase(actual.getScheme()) &&
                wanted.getHost().equalsIgnoreCase(actual.getHost()) && port(wanted) == port(actual) && actual.getUserInfo() == null;
        } catch (URISyntaxException | NullPointerException error) { return false; }
    }

    private static int port(URI uri) {
        return uri.getPort() != -1 ? uri.getPort() : ("https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80);
    }

    private static boolean privateHost(String host) {
        if (host.equals("localhost")) return true;
        String[] values = host.split("\\.");
        if (values.length != 4) return false;
        int[] parts = new int[4];
        for (int index = 0; index < 4; index++) {
            if (!values[index].matches("0|[1-9][0-9]{0,2}")) return false;
            parts[index] = Integer.parseInt(values[index]);
            if (parts[index] > 255) return false;
        }
        return parts[0] == 10 || parts[0] == 127 || (parts[0] == 192 && parts[1] == 168) ||
            (parts[0] == 172 && parts[1] >= 16 && parts[1] <= 31);
    }
}
