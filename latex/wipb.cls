%%
%% This is file `wipb.cls`.
%%
\NeedsTeXFormat{LaTeX2e}[1995/12/01]
\ProvidesClass{wipb}[2009/07/31 v1.3 LaTeX document class (MZ)]

\DeclareOption*{%
	\PassOptionsToClass{\CurrentOption}{mbook}%
}
\ExecuteOptions{inzynierska,a4paper,12pt,oneside}
\ProcessOptions %\relax

\LoadClass[oneside,12pt]{mbook}
\let\lll\undefined
\usepackage[utf8]{inputenc}
\usepackage[table]{xcolor}
\RequirePackage{graphicx}
\RequirePackage[colorlinks,plainpages=false,
 pdfpagelabels,
 naturalnames=true]{hyperref}
\RequirePackage[tableposition=top]{caption}
\RequirePackage{listings}
\RequirePackage{multirow}
\RequirePackage[linesnumbered,ruled,vlined]{algorithm2e}%algorytmy
\RequirePackage{tikz}
\RequirePackage{amssymb}
\RequirePackage{indentfirst}
\RequirePackage{t1enc}
\RequirePackage{lmodern}
% \RequirePackage{times}
\RequirePackage[a4paper, top=2.5cm, bottom=2.5cm, left=3.5cm, right=2cm]{geometry}
\RequirePackage{setspace}
\RequirePackage{MnSymbol}
\usepackage{breakurl}
\usepackage{epigraph}
\usepackage{makecell}
%\usetikzlibrary{arrows.meta, positioning, shapes.geometric}
%\usetikzlibrary{positioning, fit, backgrounds, arrows.meta}
\definecolor{Gray}{gray}{0.68}
\definecolor{LightGray}{gray}{0.93}
\definecolor{LightGreen}{RGB}{149,222,149}
\definecolor{LightRed}{RGB}{222,149,149}
%\pgfkeys{%
%  /tikz/on layer/.code={
%    \pgfmainlayersheet
%    \pgfsetlayer{#1}%
%  }
%}
\pagestyle{headings}
\parindent=1cm
\linespread{1.5}

%definicje odstepow
%\hoffset -1 in
%\textwidth 15.5 cm
%\voffset -1 in
%\textheight 23.5 cm
%\oddsidemargin = 3.5cm
%\evensidemargin = 3.5cm
%\topmargin = 1.5 cm
\footskip = 35pt

\hyphenpenalty=2000			% nie dziel wyrazów zbyt często
\clubpenalty=10000			% kara za sierotki
\widowpenalty=10000			% nie pozostawiaj wdów
\brokenpenalty=10000		% nie dziel wyrazów między stronami
\exhyphenpenalty=999999		% nie dziel słów z myślnikiem
\righthyphenmin=4			% dziel minimum 3 litery

\tolerance=4500
\pretolerance=250
\hfuzz=1.5pt
\hbadness=1450

\sloppy

% styl listnigów
\lstset{
 basicstyle=\footnotesize\ttfamily,
 captionpos=b,
 numbers=none,
 frame=single,
 lineskip={-1.5pt},
 prebreak=\raisebox{0ex}[0ex][0ex]{\ensuremath{\rhookswarrow}},
 postbreak=\raisebox{0ex}[0ex][0ex]{\ensuremath{\rcurvearrowse\space}},
 breaklines=true,
 breakatwhitespace=true
}

% obrazki w wyzszej rozdzielczosci
\def\imagesdraft{d}
\def\imagesoriginal{o}
\edef\imagesversion{\imagesoriginal}

\def\katedra#1{\gdef\@katedra{#1}}
\def\typpracy#1{\gdef\@typpracy{#1}}
\def\temat#1{
\gdef\@temat{#1}
\title{#1}
}
\def\autor#1{\gdef\@autor{#1} \author{#1}}
\def\specialisation#1{\gdef\@specialisation{#1}}
\def\subject#1{\gdef\@subject{#1}}
\def\promotor#1{\gdef\@promotor{#1}}
\def\supervisor#1{\gdef\@supervisor{#1}}
\def\indeks#1{\gdef\@indeks{#1}}
\def\studia#1{\gdef\@studia{#1}}
\def\rokakademicki#1{\gdef\@rokakademicki{#1}}
\def\profil#1{\gdef\@profil{#1}}
\def\kierunekstudiow#1{\gdef\@kierunekstudiow{#1}}
\def\specjalnosc#1{\gdef\@specjalnosc{#1}}
\def\zakres#1{\gdef\@zakres{#1}}
\newcounter{@zak}

\newcommand{\mcolumns}[4]{
\multicolumn{#1}{#2}{\parbox{#3\textwidth}{#4}}
}

\newcommand{\mpbox}[1]{
\parbox{.3\textwidth}{\centering #1}
}

\newcolumntype{a}{>{\columncolor{Gray}}c}
\newcolumntype{!}{>{\global\let\currentrowstyle\relax}}
\newcolumntype{^}{>{\currentrowstyle}}
\newcommand{\rowstyle}[1]{\gdef\currentrowstyle{#1}%
  #1\ignorespaces
}

\newcommand{\multilinecell}[2][c]{%
  \begin{tabular}[#1]{@{}c@{}}#2\end{tabular}}
\newcommand{\myvec}[1]{\ensuremath{\begin{bmatrix}#1\end{bmatrix}}}

% \AtBeginDocument{%
%   \renewcommand{\tablename}{Tabela}%
%   \renewcommand{\listtablename}{Spis tabel}%
% }

\def\clearheadinfo{\gdef\@autor{Brak autora}%
                  \gdef\@temat{Brak Tytułu}%
                  \gdef\@institute{Brak Katedry}%
}

\renewenvironment{titlepage}{%
%%%%%%%%%strona tytulowa%%%%%%%%%%
    \cleardoublepage
    \if@twocolumn
      \@restonecoltrue\onecolumn
    \else
      \@restonecolfalse\newpage
    \fi
    \thispagestyle{empty}%
  }%
  {\if@restonecol\twocolumn \else \newpage \fi}


\clearheadinfo
\renewcommand\maketitle{%
    \begin{titlepage}
        \begin{center}
        \linespread{1.0}
            \vspace{\stretch{2}}
            {\includegraphics{grafika/logopjatk.jpg}\par}
            \vspace{\stretch{1}}
            {\Large\textbf{\textsc{Wydział Informatyki}}\par}
            \vspace{\stretch{1}}
            {\Large\textbf{\textsc{\@katedra}}\par}
            {\large\textsc{\@specjalnosc}\par}
            \vspace{\stretch{1}}
            {\Large\textbf{\textsc{\@autor}} \par}
            {\Large\textsc{\@indeks} \par}
            \vspace{\stretch{1}}
            {\LARGE\textbf{\textsc{\@temat}}\par}
            \begin{flushright}
                \vspace{\stretch{1}}
                {\Large\textsc{Praca dyplomowa \@typpracy}\par}
                \vspace{\stretch{1}}
                {\Large\textsc{Promotor: \@promotor} \par} 
                \vskip 2em
            \end{flushright}
            \vspace{\stretch{2}}
            {\Large\textsc{Warszawa, czerwiec \number\year }\ r.\par}
       \end{center}
   \end{titlepage}
    
    % PONIŻEJ ZNAJDUJE SIĘ SZABLON DO ANGIELSKIEJ WERSJI PRACY
    % \begin{titlepage}
    %     \linespread{1.0}
    %     \begin{center}
    %         \vspace{\stretch{2}}
    %         {\includegraphics{grafika/logopjatk.jpg}\par}
    %         \vspace{\stretch{1}}
    %         {\Large\textbf{\textsc{Computer Science Faculty}}\par}
    %         \vspace{\stretch{1}}
    %         {\Large\textbf{\textsc{Computer Networks}}\par}
    %         {\large\textsc{\@specialisation}\par}
    %         \vspace{\stretch{1}}
    %         {\Large\textbf{\textsc{\@autor}} \par}
    %         {\Large\textsc{\@indeks} \par}
    %         \vspace{\stretch{1}}
    %         {\LARGE\textbf{\textsc{\@subject}}\par}
    %         \begin{flushright}
    %             \vspace{\stretch{1}}
    %             {\Large\textsc{Bachelor of Engineering Thesis}\par}
    %             \vspace{\stretch{1}}
    %             {\Large\textsc{Supervisor: \@supervisor} \par} 
    %             \vskip 2em
    %         \end{flushright}
    %         \vspace{\stretch{2}}
    %         {\Large\textsc{Warsaw, January \number\year }\par}
    %     \end{center}
    % \end{titlepage}
}

%% spolszczenia
\renewcommand{\algorithmcfname}{Algorytm}%
\renewcommand{\algocf@typo}{}%
\renewcommand{\@algocf@procname}{Procedura}
\renewcommand{\@algocf@funcname}{Funkcja}
\renewcommand{\lstlistingname}{Listing} %Nagłówek listingu

\endinput