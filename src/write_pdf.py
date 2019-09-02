#!/usr/bin/env python

from astropy.io import fits
import ConfigParser
import datetime
import log
import matplotlib
# matplotlib.use('Agg')
from matplotlib import pyplot
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.pyplot import table
from pyraf import iraf
import numpy
import os
import re
import utils


# ----------------------------------------------------------------------------------------------------------------------
def start(configfile):

    logger = log.getLogger('write')

    config = ConfigParser.RawConfigParser()
    config.optionxform = str  # make options case-sensitive
    config.read(configfile)

    iraf.onedspec()

    for path, process in config.items("ScienceDirectories"):  # Returns list of (variable, value) pairs
        logger.debug('%s = %s', path, process)

        if not process:
            logger.debug('Skipping %s', path)
            continue

        pdf = PdfPages(path + '/Final/data_sheet.pdf')

        sci = imexam(path)
        tel = imexam(path + '/Telluric')

        sci['SNR'] = estimate_snr(path + '/Intermediate/ zbduvsrc_comb_order3_MEF.fits[1]')       # flam1.fits
        tel['SNR'] = estimate_snr(path + '/Telluric/Intermediate/hvsrc_comb_order3_SEF.fits')  # ftell_nolines1

        sci['PARANGLE'] = parallactic(dec=float(sci['DEC']),
                                      ha=hms2deg(sci['HA']),
                                      lat=location(sci['OBSERVAT'])['latitude'],
                                      az=float(sci['AZIMUTH']), units='degrees')

        tel['PARANGLE'] = parallactic(dec=float(tel['DEC']),
                                      ha=hms2deg(tel['HA']),
                                      lat=location(tel['OBSERVAT'])['latitude'],
                                      az=float(tel['AZIMUTH']), units='degrees')

        logger.debug('SCI: %s', sci)
        logger.debug('TEL: %s', tel)

        fig = pyplot.figure()
        ax = fig.add_subplot(211, frame_on=False)
        ax.xaxis.set_visible(False)
        ax.yaxis.set_visible(False)

        # TOP TABLE:
        labels = [sci['GEMPRGID'] + '\n' + sci['DATE-OBS'], 'Total counts, K', 'FWHM ("), K', "S/N, 2.1-2.2 um", 'Airmass', 'HA']
        text = [[sci['OBJECT'], sci['PEAK'], sci['FWHM'], sci['SNR'], sci['AIRMASS'], sci['HA']],
                [tel['OBJECT'], tel['PEAK'], tel['FWHM'], tel['SNR'], tel['AIRMASS'], tel['HA']]]
        table(cellText=text, colLabels=labels, loc='upper center')

        # BOTTOM TABLE:
        labels = [sci['GEMPRGID'] + '\n' + sci['DATE-OBS'], 'Slit Angle', 'Par. Angle', 'Diff', 'IQ', 'CC', 'WV', 'SB']
        text = [[sci['OBJECT'], sci['PA'], sci['PARANGLE'], abs(sci['PA'] - sci['PARANGLE']), sci['RAWIQ'], sci['RAWCC'], sci['RAWWV'], sci['RAWBG']],
                [tel['OBJECT'], tel['PA'], tel['PARANGLE'], abs(tel['PA'] - tel['PARANGLE']), tel['RAWIQ'], tel['RAWCC'], tel['RAWWV'], tel['RAWBG']]]
        table(cellText=text, colLabels=labels, loc='center')

        version = '0.9'  # TODO: Fix the version
        date = datetime.datetime.now()
        ax.text(0.0, 0.28, 'GNIRS-Pype version ' + version + ",  " + str(date), size=5)

        # TODO: Query Simbad for the target redshift and add to config file.
        #   Possibly do it at the same time as standard star lookup?

        ax = fig.add_subplot(212)

        sci_wave, sci_flux = numpy.loadtxt(path + '/Final/' + sci['OBJECT'] + '_src.txt', unpack=True)
        pyplot.plot(sci_wave, sci_flux, color='black', marker='', linestyle='-', linewidth=0.5, label=sci['OBJECT'])
        pyplot.ylim(0.0, 1.1 * numpy.amax(sci_flux))  # force a lower limit of zero

        vega_wave, vega_flux = numpy.loadtxt(config.get('defaults', 'runtimeData') + 'vega.txt', unpack=True)
        # TODO:  if redshift:  vega_wav = vega_wav / (1 + redshift)
        vega_flux *= 1.05 * numpy.amax(sci_flux) / numpy.amax(vega_flux)
        pyplot.plot(vega_wave, vega_flux, color='blue', marker='', linestyle='--', linewidth=0.5, label='Vega')

        # TODO: if flux calibrated set the proper axes labels:
        ylabel = r'erg cm$^{-2}$ s$^{-1}\ \AA^{-1}$'
        # ylabel = r'F$_{\lambda}$, arbitrary units'
        pyplot.ylabel(ylabel, size=8)
        # xlabel should be either "Rest" or "Observed" depending on whether a redshift was found and corrected for:
        xlabel = r'Observed wavelength, $\mu$m'
        pyplot.xlabel(xlabel, size=8)
        fig.tight_layout()
        pyplot.legend(loc='best', fancybox=True, numpoints=1, prop={'size': 6})
        pyplot.grid(linewidth=0.25)
        pdf.savefig(fig)
        pyplot.close(fig)

        # --------------------------------------------------------------------------------------------------------------
        # Plot the separate orders so the user can judge if there are any unacceptable offsets
        # and edit the regions used for combining if they like:

        regions = {}
        for order, r in config.items('orderScalingRegions'):
            regions[int(order)] = r
        logger.debug('orderScalingRegions: %s', regions)

        prefix = \
            config.get('runtimeFilenames', 'finalPrefix') + \
            config.get('runtimeFilenames', 'fluxCalibPrefix') + \
            config.get('runtimeFilenames', 'dividedTelContinuumPrefix') + \
            config.get('runtimeFilenames', 'telluricPrefix') + \
            config.get('runtimeFilenames', 'extractRegularPrefix')
        combinedsrc = config.get('runtimeFilenames', 'combinedsrc')

        plot_orders(
            filelist=utils.make_list(prefix + utils.nofits(combinedsrc), regions=regions, suffix='.txt'),
            path=path + '/Intermediate/',
            output=pdf)

        if config.getboolean('extractSpectra1D', 'extractFullSlit'):
            plot_orders("flamfull", "../PRODUCTS/orders_fullslit.pdf")

        if config.getboolean('extractSpectra1D', 'extractStepwise'):
            for k in range(1, steps):
                plot_orders("flamstep"+str(k)+"_", "../PRODUCTS/orders_step"+str(k)+".pdf")

        pdf.close()

    return


# ----------------------------------------------------------------------------------------------------------------------
def imexam(path, ypos=340):
    """
    Measure the spectrum peak and FWHM
    :param path: target path of image to measure
    :param ypos: Y-position to perform measurements [340 pix]
    :return: dictionary of measurements {? overkill for only 2 values ?}
    """
    logger = log.getLogger('datasheet.imexam')

    fits_file = 'Intermediate/src_comb.fits'
    ap_file = 'Intermediate/database/apsrc_comb_SCI_1_'

    original_path = os.getcwd()
    iraf.chdir(path)  # This shouldn't be necessary, but IRAF has path length limits

    with open(ap_file, 'r') as f:
        for line in f.readlines():
            if 'center' in line:
                xpos = float(line.split()[1])
                break
    logger.debug('Spectrum X-position: %.2f pix', xpos)

    cursor = 'tmp.cur'  # Write a cursor file for imexam
    with open(cursor, 'w') as f:
        f.write('%.3f %.3f\n' % (xpos, ypos))

    logger.info('Running IRAF imexam to measure the spectrum peak and FHWM...')
    iraf.unlearn(iraf.imexam)
    iraf.unlearn(iraf.jimexam)    # jimexam = 1-dimensional gaussian line fit
    # iraf.jimexam.naverage = 50  # Number of lines, columns, or width perpendicular to a vector to average
    # iraf.jimexam.width = 100    # Width of background region for background subtraction (pix)
    # iraf.jimexam.rplot = 100    # Radius to which the radial profile or 1D profile fits are plotted (pix)
    # iraf.jimexam.sigma =        # Initial sigma (pix)
    # iraf.imexam.graphics = 'stgkern' #  Force the use of the standard IRAF graphics kernel
    logger.debug('iraf.jimexam.sigma = %0.3f', iraf.jimexam.sigma)
    logger.debug('iraf.jimexam.naverage = %0.3f', iraf.jimexam.naverage)
    logfile = 'tmp.log'

    iraf.imexam(
        input=fits_file + '[SCI,1]', frame=1, output='', logfile=logfile, keeplog='yes', defkey='j',
        ncstat=5, nlstat=5, imagecur=cursor, use_display='no', Stdout=1)

    logger.debug('Parsing imexam results from the log file...')
    peak = None
    fwhm = None
    with open(logfile) as f:
        for line in f:
            if '#' in line:
                continue
            logger.debug('%s', line.strip())
            vals = line.replace('=', ' ').split()
            if vals[0] == 'Lines':      # record measure of x center
                center = float(vals[3])
                peak = float(vals[5])
                fwhm = float(vals[9])
                break
    logger.debug('center = %s  peak = %s  fwhm = %s', center, peak, fwhm)
    data = {'PEAK': peak, 'FWHM': fwhm}

    logger.debug('Cleaning up...')
    for f in [cursor, logfile]:
        os.remove(f)

    logger.debug('Reading some FITS header keywords...')
    header = fits.open(fits_file)[0].header
    for key in ['GEMPRGID', 'AIRMASS', 'RA', 'DEC', 'HA', 'AZIMUTH', 'PA',
                'OBSERVAT', 'RAWIQ', 'RAWCC', 'RAWWV', 'RAWBG', 'DATE-OBS']:
        try:
            data[key] = header[key].strip() if isinstance(header[key], str) else header[key]
        except:
            logger.warning('%s[%s] is undefined', f, key)
            data[key] = None

    data['OBJECT'] = re.sub('[^a-zA-Z0-9]', '', header['OBJECT'])  # replace non-alphanumeric characters

    iraf.chdir(original_path)

    logger.debug('data: %s', data)
    return data


# ----------------------------------------------------------------------------------------------------------------------
def estimate_snr(onedspectrum, wav1=21000, wav2=22000, interactive=False):
    """
    Estimate Signal-to-Noise ratio

    :param onedspectrum: input one-dimensional (extracted) spectrum
    :param wav1: starting wavelength rof ange to fit and measure
    :param wav2: ending wavelength of range to fit and measure
    :param interactive:
    :return: signal-to-noise ratio (float)
    """

    logger = log.getLogger('datasheet.snr')
    logger.info('Estimating S/N...')

    output = 'tmp.fits'
    stdout = 'tmp.out'
    cursor = 'tmp.cur'
    logfile = 'tmp.log'

    with open(cursor, 'w') as f:  # Generate a cursor file for bplot
        f.write('%d 0 1 m\n' % wav1)
        f.write('%d 0 1 m\n' % wav2)
        f.write('q')

    logger.debug('continuum input: %s', onedspectrum)
    logger.debug('sample: %d:%d', wav1, wav2)

    iraf.sfit.logfile = logfile
    iraf.continuum(
        input=onedspectrum, output=output, lines='*', bands='1', type='ratio', replace=False, wavescale=True,
        logscale=False, override=False, logfile=logfile, interactive=interactive, sample='%d:%d' % (wav1, wav2),
        naverage=1, function='spline3', order=3, low_rej=2, high_rej=3, niterate=5, grow=1)

    iraf.splot.save_file = logfile
    iraf.bplot(
        images=output, apertures="", band=1, cursor=cursor, next_image="",
        new_image="", overwrite="no", spec2="", constant=0.0, wavelength=0.0, linelist="",
        wstart=0.0, wend=0.0, dw=0.0, boxsize=2, Stdout=stdout)  # graphics="stgkern", StdoutG="dev$null")

    logger.debug('Parsing output...')
    snr = None
    with open(stdout, 'r') as f:
        for line in f.readlines():
            if 'snr' in line:
                snr = float(line.split()[-1])
    logger.debug('SNR: %s', snr)

    for f in [cursor, logfile, output, stdout]:
        os.remove(f)

    return snr


# ----------------------------------------------------------------------------------------------------------------------
def parallactic(dec, ha, lat, az, units='degrees'):
    """
    Compute the parallactic angle
    :param dec:  target declination
    :param ha:   hour angle
    :param lat:  observatory latitude
    :param az:   target azimuth
    :param units:  degrees or radians for input and ouput quantities
    :return:     parallactic angle (float)
    """
    logger = log.getLogger('parallactic')

    if units == 'degrees':
        dec *= numpy.pi / 180.
        ha *= numpy.pi / 180.
        lat *= numpy.pi / 180.
        az *= numpy.pi / 180.

    if numpy.cos(dec) != 0.0:
        sinp = -1.0*numpy.sin(az)*numpy.cos(lat)/numpy.cos(dec)
        cosp = -1.0*numpy.cos(az)*numpy.cos(ha)-numpy.sin(az)*numpy.sin(ha)*numpy.sin(lat)
        pa = numpy.arctan2(sinp, cosp)
    else:
        if lat > 0.0:
            pa = numpy.pi
        else:
            pa = 0.0

    if units == 'degrees':
        pa *= 180. / numpy.pi

    logger.debug('Parallactic Angle: %.3f %s', pa, units)
    return pa


# ----------------------------------------------------------------------------------------------------------------------
def hms2deg(angle):
    """Convert sexagesimal HH:MM:SS.sss to decimal degrees"""
    h, m, s = angle.split(':')
    hours = float(h) + float(m)/60. + float(s)/3600.
    return hours / 24. * 360.


# ----------------------------------------------------------------------------------------------------------------------
def location(observatory):
    """Return the observatory location as a dictionary"""
    if observatory == 'Gemini-North':
        latitude = 297.35709        # 19:49:25.7016
        longitude = -155.46906      # -155:28:08.616
        elevation = 4213            # meters
    elif observatory == 'Gemini-South':
        latitude = 453.61125        # -30:14:26.700
        longitude = -70.7366933333  # -70:44:12.096
        elevation = 2722            # meters
    else:
        raise SystemExit('Unknown observatory')
    return {'latitude': latitude, 'longitude': longitude, 'elevation': elevation}


# ----------------------------------------------------------------------------------------------------------------------
def plot_orders(filelist, path, output):
    logger = log.getLogger('plot_orders')
    logger.debug('filelist: %s', filelist)
    logger.debug('path: %s', path)
    logger.debug('output: %s', output)

    fig = pyplot.figure()
    goodbits = []

    for f in filelist:
        filename, start, end, junk = re.split(r'[\[:\]]', f)
        start = int(start)
        end = int(end)
        logger.debug('filename: %s', filename)
        logger.debug('start: %s, end: %s', start, end)
        wave, flux = numpy.loadtxt(path + filename, unpack=True)
        pyplot.plot(wave, flux, color='red', marker='', linestyle='-', linewidth=0.5)  # label the orders?
        pyplot.plot(wave[start:end], flux[start:end], color='green', marker='', linestyle='-', linewidth=0.5)
        goodbits.extend(flux[start:end])

    pyplot.ylim(numpy.amin(goodbits), 1.05 * numpy.amax(goodbits))
    pyplot.xlabel(r"$\mu$m, observed")
    pyplot.ylabel(r"F$_{\lambda}$")
    output.savefig(fig)
    pyplot.close(fig)
    return


# ----------------------------------------------------------------------------------------------------------------------
if __name__ == '__main__':
    log.configure('gnirs.log', filelevel='INFO', screenlevel='DEBUG')
    start('gnirs.cfg')
