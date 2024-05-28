#!/usr/bin/php
<?php

/* Decode json file to php object */
function DecodeJsonFile($file)
{
	$content = @file_get_contents($file);
	if (FALSE === $content) {
		echo $file . ": Read error.\n";
		return NULL;
	}

	$result = json_decode($content, true);
	if (!is_array($result)) {
		echo $file . ": Json parse failed.\n";
	}
	return $result;
}

function HasExternalDepend(&$dstConfig, &$comp)
{
	if (array_key_exists($comp, $dstConfig)) {
		$compConfig = $dstConfig[$comp];

		if (array_key_exists('depend', $compConfig)) {
			foreach ($compConfig['depend'] as $item) {
				if (HasExternalDepend($dstConfig, $item)) {
					return true;
				}
			}
		}

		return false;
	} else {
		return true;
	}
}

function GenerateCompassConfig()
{

	$compassConfig = <<<EOD
# Get the directory that this configuration file exists in
dir = File.dirname(__FILE__)

load File.join(dir, '../../../resources/scss/src')

ext_dir = "/usr/syno/synoman/scripts/ext-3.4/ux/scss/src"
# compatibility with 6.0
ext_dir = "/source/synojslib/ext-3.4/ux/scss/src" unless File.directory?(ext_dir)
add_import_path ext_dir

syno_ext_dir = "/usr/syno/synoman/synoSDSjslib/scss"
# compatibility with 6.0
syno_ext_dir="/source/synoSDSjslib/scss" unless File.directory?(syno_ext_dir)
add_import_path syno_ext_dir

# Compass configurations
sass_path    = dir
css_path     = File.join(dir, "..")
images_path  = "/usr/syno/synoman/scripts/ext-3.4/ux"
# compatibility with 6.0
images_path  = "/source/synojslib/ext-3.4/ux" unless File.directory?(images_path)
environment  = :production
output_style = :compressed
sprite_load_path = File.join(dir, "../images")
http_path	 = "./"
generated_images_dir = "../images"

module Sass::Script::Functions

  def real_path(image_file)
    if Compass.configuration.images_path
      File.join(Compass.configuration.images_path, image_file)
    else
      File.join(Compass.configuration.project_path, image_file)
    end
  end

  def md5(filename)
    if filename && File.exist?(filename)
      digest = Digest::MD5.new()
      digest << File.read(filename)
      unquoted_string(digest.hexdigest)
    else
      Compass::Util.compass_warn(
        "File not found: #{filename}, cannot do prevent cache signature."
      )
      unquoted_string('no_image_found')
    end
  end
  def syno_md5(image_file)
    image_file = image_file.respond_to?(:value) ? image_file.value : image_file
    if File.exists?(image_file)
      md5(image_file)
    else
      md5(real_path(image_file))
    end
  end
end

EOD;

	return $compassConfig;
}

function GenerateMakefile($compress)
{
	global $ConfigDefine;

	if (true === $compress) {
		echo "Compress to Gzip: [{$compress}]\n";
	}

	$JSTarget = array();
	foreach ($ConfigDefine as $dstFile => $srcFiles) {
		array_push($JSTarget, $dstFile);
	}

	$CompressedFiles = implode(' ', array_keys($ConfigDefine));
	$Makefile = <<<EOD
include /env.mak

JS_COMPILER=/usr/local/tool/shrinksafe.php $(JS_COMPILER_ARGV)
SASS_COMPILER=/usr/bin/compass $(SASS_COMPILER_ARGV)
CONFIG_PARSER=/usr/syno/bin/GenerateModuleFiles.php
JS_DEPENDER=/usr/syno/bin/GenerateJSDepend.php
AUTO_CONFIG_TOOL=/usr/local/tool/parse_requires.py

CONFIGFILE=config
STYLEFILE=style.css
SCSS_FILE=scss/style.scss
SASS_CACHE=scss/.sass-cache
COMPASS_CONFIG=scss/config.rb
JSFILES={$CompressedFiles}
JS_INPUT=$(shell /usr/bin/find $(JS_DIR) -name "*.js")

TARGET_JSCompress=CSSCompress config.depends \$(JSFILES)
TARGET_install=install_CSSCompress
TARGET_clean=clean_CSSCompress

ifneq ("$(wildcard app.config)","")
	DEBUGFILE:=auto_config.debug
else
	DEBUGFILE:=config.debug
endif

USE_COMPRESS_GZIP={$compress}
ifeq ("\$(SYNOCOMPRESS)", "")
	USE_COMPRESS_GZIP=no
endif

ifeq ("\$(USE_COMPRESS_GZIP)", "yes")
	STYLEFILE_GZIP:=$(addsuffix .gz, $(STYLEFILE))
	JSFILES_GZIP:=$(addsuffix .gz, $(JSFILES))
	TARGET_install+=install_GzipCompress
	TARGET_clean+=clean_GzipCompress
endif

JSCompress: $(TARGET_JSCompress)
JSCompress_AutoConfig: $(TARGET_JSCompress)

CSSCompress:
	if [ -f \$(SCSS_FILE) ]; then \$(SASS_COMPILER) compile scss; fi

clean_JSCompress: $(TARGET_clean)
	if [ -n "\$(JSFILES)" ]; then rm -f \$(JSFILES); fi
	if [ -n "auto_config.debug" ]; then rm -f auto_config.debug; fi
	if [ -n "config.depends" ]; then rm -f config.depends; fi
	if [ -n "config" ]; then rm -f config; fi

clean_CSSCompress:
	if [ -f \$(SCSS_FILE) ]; then rm -f \$(STYLEFILE); fi
	if [ -d \$(SASS_CACHE) ]; then rm -rf \$(SASS_CACHE); fi

clean_GzipCompress:
	if [ -n "\$(JSFILES_GZIP)" ]; then rm -f \$(JSFILES_GZIP); fi
	if [ -f "\$(STYLEFILE_GZIP)" ]; then rm -f \$(STYLEFILE_GZIP); fi

install_JSCompress: $(TARGET_install)
	[ -d  \$(INSTALLDIR) ] || install -d \$(INSTALLDIR)
	if [ -f \$(CONFIGFILE) ]; then cp \$(CONFIGFILE) \$(INSTALLDIR); fi
	if [ -n "\$(JSFILES)" ]; then cp \$(JSFILES) \$(INSTALLDIR); fi
	if [ -f \$(STYLEFILE) ]; then cp -f \$(STYLEFILE) \$(INSTALLDIR); fi

install_CSSCompress:
	# already install style.css install_JSCompress

install_GzipCompress: \$(JSFILES) CSSCompress
	if [ -f "\$(STYLEFILE)" ] && [ -s "\$(STYLEFILE)" ]; then \$(SYNOCOMPRESS) \$(STYLEFILE); fi
	if [ -n "\$(JSFILES)" ]; then \$(SYNOCOMPRESS) \$(JSFILES); fi
	[ -d  "\$(INSTALLDIR)" ] || install -d \$(INSTALLDIR)
	if [ -f "\$(STYLEFILE_GZIP)" ]; then cp -f \$(STYLEFILE_GZIP) \$(INSTALLDIR); fi
	for JSFILE in $(JSFILES_GZIP); do \
		if [ -f "\$\$JSFILE" ]; then cp -f \$\$JSFILE $(INSTALLDIR); fi \
	done

auto_config.debug: app.config config.define \$(JS_INPUT)
	\$(AUTO_CONFIG_TOOL) --makegoal=\$(MAKECMDGOALS) \$(JS_DIR) \$(JS_NAMESPACE)

config.depends: $(DEBUGFILE) config.define
	\$(JS_DEPENDER) \$(shell pwd)


EOD;

	foreach ($ConfigDefine as $dstFile => $dstConfig) {
		if(isSet($ConfigDefine[$dstFile]['JSfiles']) && isSet($ConfigDefine[$dstFile]['params'])) {
			$Makefile .= $dstFile . ': config.depends ' . implode(' ', $ConfigDefine[$dstFile]['JSfiles']) . "\n";
			$Makefile .= "\t$(JS_COMPILER) " . $ConfigDefine[$dstFile]['params'] . " -d ". $dstFile ." \"\$(shell pwd)/config.depends\"\n\n";
		} else {
			$Makefile .= $dstFile . ': config.depends ' . implode(' ', $dstConfig) . "\n";
			$Makefile .= "\t$(JS_COMPILER) -d ". $dstFile ." \$(shell pwd)/config.depends\n\n";
		}
	}

	return $Makefile;
}

function Usage()
{
	global $argv;

	echo <<<EOD
Usage: {$argv[0]} [-c yes|no] moduleDir
	-c yes|no:
		yes: Compress .css and .js to .gz
		no: Don't compress to .gz

EOD;
}

/* ----------------------- */
/* ----------------------- */
/* main access entry point */
/* ----------------------- */
/* ----------------------- */

function GetOptions()
{
	global $argv, $argc;

	$options = "c:";
	$opts = getopt($options);
	foreach( $opts as $o => $a )
	{
		while ( $k = array_search( "-" . $o, $argv ) ) {
			if ( $k ) {
				unset( $argv[$k] );
				$argc--;
			}
			if ( preg_match( "/^.*".$o.":.*$/i", $options ) ) {
				unset( $argv[$k+1] );
				$argc--;
			}
		}
	}
	$argv = array_merge( $argv );
	return $opts;
}

$opts = GetOptions();

if (FALSE === $opts || $argc < 2 || $argc > 3) {
	Usage();
	exit(1);
}

/* Compress package's js, css to gzip */
$UseCompressGzip="yes";
if (file_exists("/lnxscripts")) {
	$UseCompressGzip = "no";
} else if (isSet($opts['c'])) {
	switch ($opts['c']) {
		case "yes":
			$UseCompressGzip = "yes";
			break;
		case "no":
			$UseCompressGzip = "no";
			break;
		default:
			echo "Error: Invalid Transpiler Option.\n";
			Usage();
			exit(1);
	}
}

if (!is_dir($argv[1])) {
	echo "Error: {$argv[1]} is not a directory.\n";
	exit(1);
}

$CWD = getcwd();
chdir($argv[1]);

$InputFiles = array(
	'debug'		=>	'config.debug',
	'define'	=>	'config.define',
	'auto_debug'=>	'auto_config.debug',
	'depend'	=>	'config.depends'
);

$OutputFiles = array(
	'config'	=>	'config',
	'makefile'	=>	'Makefile.js.inc',
	'style'		=>	'style.css',
	'scss'		=>	'scss/style.scss',
	'compass_config'	=>	'scss/config.rb'
);

if (file_exists("app.config") && file_exists("config.debug"))  {
	echo "Error > app.config and config.debug should not both exist\n";
	exit(1);
}

$define_path = $InputFiles['define'];

if (file_exists($define_path)) {
	$ConfigDefine = DecodeJsonFile($define_path);
} else {
	echo "Skip parsing: config.define not exist\n";
	$ConfigDefine = array();
}

if (!is_array($ConfigDefine)) {
	exit(1);
}

/* Generate files */
file_put_contents($OutputFiles['makefile'], GenerateMakefile($UseCompressGzip));

// generate config.rb for compass if scss file exists
if (file_exists($OutputFiles['scss'])) {
	file_put_contents($OutputFiles['compass_config'], GenerateCompassConfig());
}

chdir($CWD);

?>

