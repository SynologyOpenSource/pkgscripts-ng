#!/bin/bash
# Copyright (c) 2000-2016 Synology Inc. All rights reserved.

pkg_warn() {
	local ret=$?
	echo "Error: $@" >&2
	return $?
}

pkg_log() {
	local ret=$?
	echo "$@" >&2
	return $ret
}

get_var_from_envmak() {
	local var="$1"
	shift
	local envmaks="$@"
	local ret=
	local defaultSearchPath="/env.mak /env32.mak"

	for f in "${envmaks[@]}" $defaultSearchPath; do
		if [ ! -r "$f" ]; then
			continue
		fi

		ret=$(grep "^$var=" "$f" | cut -d= -f2)

		if [ -n "$ret" ]; then
			break
		fi
	done

	if [ -z "$ret" ]; then
		pkg_warn "get_var_from_envmak: can not extract $var from '[$envmaks $defaultSearchPath]'"
		return 1
	else
		echo "$ret"
	fi
}

pkg_get_platform() { # [path of env.mak (default: /env.mak)]
	# @see synopkg/lib/pkgtool.cpp:77: gSystemArchMapping
	local arch=

	local PLATFORM_ABBR=$(get_var_from_envmak PLATFORM_ABBR "$1" 2> /dev/null) || return 1
	if [ -n "$PLATFORM_ABBR" ]; then
		case "$PLATFORM_ABBR" in
			6281)		arch="88f6281" ;;
			x64)		arch="x86" ;;
			*)		arch="$PLATFORM_ABBR" ;;
		esac
	fi
	if [ -z "$arch" ]; then
		local SYNO_PLATFORM=$(get_var_from_envmak SYNO_PLATFORM "$1") || return 1
		case "$SYNO_PLATFORM" in
			MARVELL_88F6281)	arch="88f6281" ;;
			PPC_QORIQ)		arch="qoriq" ;;
			X64)			arch="x86" ;;
			BROMOLOW)		arch="bromolow" ;;
			DENVERTON)		arch="denverton" ;;
			REALTEK_RTD1296)        arch="rtd1296" ;;
			APOLLOLAKE)		arch="apollolake" ;;
			CEDARVIEW)		arch="cedarview" ;;
			AVOTON)			arch="avoton" ;;
			BRASWELL)		arch="braswell" ;;
			MARVELL_ARMADAXP)	arch="armadaxp" ;;
			MARVELL_ARMADA370)	arch="armada370" ;;
			MARVELL_ARMADA375)	arch="armada375" ;;
			EVANSPORT)		arch="evansport" ;;
			MINDSPEED_COMCERTO2K)	arch="comcerto2k" ;;
			ALPINE)			arch="alpine" ;;
			STM_MONACO)             arch="monaco" ;;
			MARVELL_ARMADA38X)      arch="armada38x" ;;
			HISILICON_HI3535)       arch="hi3535" ;;
			BROADWELL)		arch="broadwell" ;;
			KVMX64)			arch="kvmx64" ;;
			GRANTLEY)		arch="grantley" ;;
			DOCKERX64)		arch="dockerx64" ;;
			*)			arch="" ;;
		esac
	fi

	echo "$arch"
}

plat_to_unified_plat() {
	local plat="$1"
	local unified_plat=

	case "$plat" in
		x86 | bromolow | cedarview | avoton | braswell | broadwell | dockerx64 | kvmx64 | grantley | denverton | apollolake)
			unified_plat="x86 bromolow cedarview avoton braswell broadwell dockerx64 kvmx64 grantley denverton apollolake"
			;;
		# alpine and alpine4k use same define.
		alpine | alpine4k )
			unified_plat="alpine alpine4k"
			;;
		*)
			unified_plat="$plat"
			;;
	esac
	echo "$unified_plat"
}

plat_to_family() {
	local plat="$1"
	local family=

	case "$plat" in
		x86 | bromolow | cedarview | avoton | braswell | broadwell | dockerx64 | kvmx64 | grantley | denverton | apollolake)
			family="x86_64"
			;;
		evansport )
			family="i686"
			;;
		alpine | alpine4k )
			family="armv7"
			;;
		88f6281 )
			family="armv5"
			;;
		qoriq )
			family="ppc"
			;;
		rtd1296 )
			family="armv8"
			;;
		# armv7 not ready platforms.
		comcerto2k | armada370 | armada375 | armadaxp | monaco | armada38x | hi3535)
			family="$plat"
			;;
		*)
			echo "Failed to get platform family for $family" 1>&2
			echo "Please add the mapping information into pkgscripts/pkg_util.sh:pkg_get_platform_family" 1>&2
			return 1
	esac
	echo "$family"
	return 0
}

pkg_get_unified_platform() { # [path of env.mak (default: /env.mak)]
	# @see synopkg/lib/pkgtool.cpp:77: gSystemArchMapping
	local plat=$(pkg_get_platform "$1") || return 1

	plat_to_unified_plat "$plat"
}

pkg_get_platform_family() { # [path of env.mak (default: /env.mak)]
	# @see synopkg/lib/pkgtool.cpp:77: gSystemArchMapping
	local plat=$(pkg_get_platform "$1") || return 1

	plat_to_family "$plat"
}

pkg_get_spk_platform() { # [path of env.mak (default: /env.mak)]
	# @see synopkg/lib/pkgtool.cpp:77: gSystemArchMapping
	local plat=$(pkg_get_platform "$1") || return 1
	local spk_plat=
	case "$plat" in
		88f6281)
			spk_plat="88f628x"
			;;
		*)
			spk_plat="$plat"
			;;
	esac
	echo "$spk_plat"
}

pkg_get_product_name() {
	local platform=$arch
	product_name="Synology NAS"
	echo "$product_name"
}

pkg_get_os_name() {
	local platform=$arch
	case "$platform" in
		*)
			os_name="DSM"
			;;
	esac
	echo "$os_name"
}

pkg_get_string() {
	local file="$1"
	local sec="$2"
	local key="$3"
	local text="$(sed -n '/^\['$sec'\]/,/^'$key'/s/'$key'.*=[^"]*"\(.*\)"/\1/p' "$file")"
	local product_name_original="_DISKSTATION_"
	local product_name=$(pkg_get_product_name)
	local os_name_original="_OSNAME_"
	local os_name=$(pkg_get_os_name)
	local idx=0

	shift 3
	for val in "$@"; do
		text="${text/\{$idx\}/$val}"
		let idx=1+$idx
	done

	echo "$text" | sed -e "s/${product_name_original}/${product_name}/g" | sed -e "s/${os_name_original}/${os_name}/g"
}

pkg_get_spk_unified_platform() { # [path of env.mak (default: /env.mak)]
	# @see synopkg/lib/pkgtool.cpp:77: gSystemArchMapping
	local plat=$(pkg_get_platform "$1") || return 1
	local spk_unified_platform=

	case "$plat" in
		88f6281)
			spk_unified_platform="88f628x"
			;;
		x86 | bromolow | cedarview | avoton | braswell | broadwell | dockerx64 | kvmx64 | grantley | denverton | apollolake)
			spk_unified_platform="x64"
			;;
		alpine | alpine4k )
			spk_unified_platform="alpine"
			;;
		*)
			spk_unified_platform="$plat"
			;;
	esac
	echo "$spk_unified_platform"
}

pkg_dump_info() {
	local fields="package version maintainer maintainer_url distributor distributor_url arch exclude_arch model
		adminprotocol adminurl adminport firmware dsmuidir dsmappname checkport allow_altport
		startable helpurl report_url support_center install_reboot install_dep_packages install_conflict_packages install_dep_services
		instuninst_restart_services startstop_restart_services start_dep_services silent_install silent_upgrade silent_uninstall install_type
		checksum package_icon package_icon_120 package_icon_128 package_icon_144 package_icon_256 thirdparty support_conf_folder log_collector
		support_aaprofile auto_upgrade_from offline_install precheckstartstop description displayname"
	local langs="enu cht chs krn ger fre ita spn jpn dan nor sve nld rus plk ptb ptg hun trk csy"
	local f= lan= file= sec= key=

	for f in $fields; do
		if [ -n "${!f}" ]; then
			echo $f=\"${!f}\"
		fi
	done

	for lang in $langs; do
		description="description_${lang}"
		if [ -n "${!description}" ]; then
			echo "${description}=\"${!description}\""
		fi
		displayname="displayname_${lang}"
		if [ -n "${!displayname}" ]; then
			echo "${displayname}=\"${!displayname}\""
		fi
	done
}

pkg_get_tar_option() {
	local version_file="/PkgVersion"

	echo "cJf"
}

pkg_make_package() { # <source path> <dest path>
	pkg_make_inner_tarball $@
}
pkg_make_inner_tarball() { # <source path> <dest path>
	local source_path=$1
	local dest_path=$2
	local package_name="package.tgz"
	local temp_extractsize="extractsize_tmp"
	local pkg_size=
	local tar_option="$(pkg_get_tar_option)"

	# check parameters
	if [ -z "$source_path" -o ! -d "$source_path" ]; then
		pkg_warn "pkg_make_inner_tarball: bad parameters, please set source dir"
		return 1
	fi
	if [ -z "$dest_path"  -o ! -d "$dest_path" ]; then
		pkg_warn "pkg_make_inner_tarball: bad parameters, please set destination dir"
		return 1
	fi

	# add extractsize to INFO
	pkg_size=`du -sk "$source_path" | awk '{print $1}'`
	echo "${pkg_size}" >> "$dest_path/$temp_extractsize"
	echo ls $source_path \| tar $tar_option "$dest_path/$package_name" -C "$source_path" -T /dev/stdin
	ls $source_path | tar $tar_option "$dest_path/$package_name" -C "$source_path" -T /dev/stdin
}

__get_spk_name() { #<info path>
	local spk_name=
	local platform_func="$1"
	local info_path="${2:-$PKG_DIR/INFO}"
	local package_name="$3"

	. $info_path

	# construct package name
	if [ -z "$package" -o -z "$arch" -o -z "$version" ]; then
		pkg_warn "pkg_make_spk: package, arch, version can not be empty"
		return 1
	fi

	if [ "x$arch" = "xnoarch" ]; then
		spk_arch="noarch"
	elif ! spk_arch=$($platform_func); then
		spk_arch="none"
	fi

	if [ "x$arch" = "xnoarch" ]; then
		spk_arch=""
	else
		spk_arch="-"$spk_arch
	fi

	if [ -z "$package_name" ]; then
		package_name="$package";
	fi

	if [ "${NOSTRIP}" == NOSTRIP ]; then
		spk_name="$package_name$spk_arch-${version}_debug.spk"
	else
		spk_name="$package_name$spk_arch-$version.spk"
	fi
	echo $spk_name;
}

pkg_get_spk_name() { #<info path> [package name]
	__get_spk_name pkg_get_spk_platform $@
}

pkg_get_spk_unified_name() { #<info path> [package name]
	__get_spk_name pkg_get_spk_unified_platform $@
}

pkg_get_spk_family_name() { #<info path> [package name]
	__get_spk_name pkg_get_platform_family $@
}

pkg_make_spk() { # <source path> <dest path> <spk file name>
	local pack="tar cf"
	local source_path=$1
	local dest_path=$2
	local info_path="$source_path/INFO"
	local spk_name=$3
	local spk_arch=
	local temp_extractsize="extractsize_tmp"

	# check parameters
	if [ -z "$source_path" -o ! -d "$source_path" ]; then
		pkg_warn "pkg_make_spk: bad parameters, please set source dir"
		return 1
	fi
	if [ -z "$dest_path"  -o ! -d "$dest_path" ]; then
		pkg_warn "pkg_make_spk: bad parameters, please set destination dir"
		return 1
	fi

	# check INFO exists and source INFO
	if [ ! -r "$info_path" ]; then
		pkg_warn "pkg_make_spk: INFO '$info_path' is not existed"
		return 1
	fi
	spk_name=${3:-`pkg_get_spk_name $info_path`}
	# add extractsize to INFO
	pkg_size=`cat $source_path/$temp_extractsize`
	echo "extractsize=${pkg_size}" >> $info_path
	rm "$source_path/$temp_extractsize"

	echo toolkit_version=$DSM_BUILD_NUM >> $info_path
	echo "create_time=\"$(date +%Y%m%d-%T)\"" >> $info_path

	# tar .spk file
	pkg_log "creating package: $spk_name"
	pkg_log "source:           $source_path"
	pkg_log "destination:      $dest_path/$spk_name"
	$pack "$dest_path/$spk_name" -C "$source_path" $(ls $source_path)
}

[ "$(caller)" != "0 NULL" ] && return 0

usage() {
	cat >&2 <<EOF
USAGE: $(basename $0) <action> [action options...]
ACTION:
	make_spk <source path> <dest path> <spk name>
	make_package <source path> <dest path>
EOF
	exit 0
}

[ $# -eq 0 ] && usage
PkgBuildAction=$1 ; shift
case "$PkgBuildAction" in
	make_spk)	pkg_make_spk "$@" ;;
	make_package)	pkg_make_package "$@" ;;
	*)		usage ;;
esac
