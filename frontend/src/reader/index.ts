// Vite entry for the reader page (013 WI-9). Since WI-10 its CSS (the token layer plus
// this entry's stylesheet) is linked from reader.html via vite_css(); the JS is wired in
// by the page WI that migrates reader.html.
import "@shared/theme";
import "./index.css";

import { markBooted } from "@shared/boot";

markBooted("reader");
